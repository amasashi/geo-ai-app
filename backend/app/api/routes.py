import json
import logging
import math
import os
import uuid
from datetime import datetime
from typing import Any

import requests
from fastapi import APIRouter, HTTPException, Query
from shapely.geometry import Point, shape

from backend.app.core.config import (
    LIBRARY_API_KEY_ENV,
    MLIT_DATA_PLATFORM_MCP_COMMAND_ENV,
    MLIT_DATA_PLATFORM_MCP_TOOL_ENV,
    REINFOLIB_MCP_COMMAND_ENV,
    REINFOLIB_MCP_TOOL_ENV,
    get_data_platform_api_key_fingerprint,
    get_data_platform_mcp_command,
    get_library_api_key_fingerprint,
    get_reinfolib_mcp_command,
    is_data_platform_api_configured,
    is_library_api_configured,
    is_openai_configured,
)
from backend.app.schemas import MlitQuery
from backend.app.services.mcp_client import call_mcp_tool_by_name, call_mlit_mcp, extract_result_text, find_geojson

router = APIRouter()
logger = logging.getLogger(__name__)

REINFOLIB_API_BASE_URL = "https://www.reinfolib.mlit.go.jp/ex-api/external"
REINFOLIB_API_ENDPOINTS = {
    3: "XPT002",
    4: "XKT001",
    5: "XKT002",
}
REINFOLIB_API_NAMES = {
    3: "地価公示・地価調査のポイント",
    4: "都市計画区域・区域区分",
    5: "用途地域",
}


def parse_result_payload(result_text: str) -> dict | None:
    try:
        payload = json.loads(result_text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def has_only_empty_api_results(payload: dict | None) -> bool:
    if not payload:
        return False
    data = payload.get("data")
    if not isinstance(data, dict):
        return False
    api_results = data.get("api_results")
    return isinstance(api_results, list) and bool(api_results) and all(item is None for item in api_results)


def summarize_api_results(payload: dict | None) -> dict:
    if not payload:
        return {"payload_parseable": False}

    data = payload.get("data")
    if not isinstance(data, dict):
        return {"payload_parseable": True, "has_data": False}

    api_results = data.get("api_results")
    summary: dict = {
        "payload_parseable": True,
        "status": payload.get("status"),
        "map_url": data.get("map_url"),
        "api_results_is_list": isinstance(api_results, list),
    }

    if isinstance(api_results, list):
        feature_counts = []
        item_types = []
        for item in api_results:
            item_types.append(type(item).__name__)
            if isinstance(item, dict):
                item_data = item.get("data")
                features = item_data.get("features") if isinstance(item_data, dict) else None
                feature_counts.append(len(features) if isinstance(features, list) else None)
            else:
                feature_counts.append(None)
        summary.update(
            {
                "api_results_count": len(api_results),
                "api_results_all_null": all(item is None for item in api_results),
                "api_result_types": item_types,
                "feature_counts": feature_counts,
            }
        )

    return summary


def geojson_from_data_platform_payload(payload: dict | None) -> dict[str, Any] | None:
    if not payload:
        return None

    search = payload.get("search")
    if not isinstance(search, dict):
        return None

    results = search.get("searchResults")
    if not isinstance(results, list):
        return None

    features = []
    for item in results:
        if not isinstance(item, dict):
            continue
        lat = item.get("lat")
        lon = item.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": item,
            }
        )

    if not features:
        return None
    return {"type": "FeatureCollection", "features": features}


def data_platform_result_count(payload: dict | None) -> int | None:
    if not payload:
        return None
    search = payload.get("search")
    if not isinstance(search, dict):
        return None
    total = search.get("totalNumber")
    return total if isinstance(total, int) else None


def extract_data_platform_detail(payload: dict | None) -> dict[str, Any] | None:
    if not payload:
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    results = data.get("getDataResults")
    if not isinstance(results, list) or not results:
        return None
    detail = results[0]
    return detail if isinstance(detail, dict) else None


def extract_thumbnail_urls(payload: dict | None) -> list[dict[str, str]]:
    if not payload:
        return []
    urls = payload.get("thumbnailURLs")
    if not isinstance(urls, list):
        return []

    normalized = []
    for item in urls:
        if not isinstance(item, dict):
            continue
        url = item.get("URL") or item.get("url")
        if not isinstance(url, str) or not url:
            continue
        normalized.append(
            {
                "id": str(item.get("ID") or item.get("id") or ""),
                "url": url,
            }
        )
    return normalized


def latlon_to_tile(lat: float, lon: float, zoom: int = 15) -> dict[str, int]:
    lat_rad = math.radians(lat)
    scale = 1 << zoom
    x = int((lon + 180.0) / 360.0 * scale)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * scale)
    return {"z": zoom, "x": x, "y": y}


def tiles_for_api(api_id: int, tile: dict[str, int]) -> list[dict[str, int]]:
    if api_id == 3:
        return [
            tile,
            {**tile, "x": tile["x"] + 1},
            {**tile, "x": tile["x"] + 1, "y": tile["y"] - 1},
            {**tile, "y": tile["y"] - 1},
        ]
    return [tile]


def feature_contains_point(feature: dict[str, Any], lat: float, lon: float) -> bool:
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        return False
    try:
        return shape(geometry).intersects(Point(lon, lat))
    except Exception:
        return False


def filter_direct_features(api_id: int, features: list[dict[str, Any]], lat: float, lon: float) -> list[dict[str, Any]]:
    if api_id in {4, 5}:
        filtered = [feature for feature in features if feature_contains_point(feature, lat, lon)]
        return filtered or features
    return features


def fetch_direct_reinfolib_geojson(arguments: dict[str, Any], request_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    key = os.getenv(LIBRARY_API_KEY_ENV, "")
    if not key:
        return None, {"error": "missing_library_api_key"}

    lat = arguments.get("lat")
    lon = arguments.get("lon")
    target_apis = arguments.get("target_apis")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)) or not isinstance(target_apis, list):
        return None, {"error": "invalid_arguments", "arguments": arguments}

    tile = latlon_to_tile(float(lat), float(lon))
    diagnostics = []
    feature_collections = []

    for api_id in target_apis:
        endpoint = REINFOLIB_API_ENDPOINTS.get(api_id)
        if not endpoint:
            continue

        merged_features = []
        for api_tile in tiles_for_api(api_id, tile):
            params = {
                "response_format": "geojson",
                "z": api_tile["z"],
                "x": api_tile["x"],
                "y": api_tile["y"],
            }
            if api_id == 3:
                params["year"] = arguments.get("year") or datetime.now().year - 1
                if arguments.get("land_price_classification"):
                    params["priceClassification"] = arguments["land_price_classification"]

            url = f"{REINFOLIB_API_BASE_URL}/{endpoint}"
            try:
                response = requests.get(
                    url,
                    params=params,
                    headers={"Ocp-Apim-Subscription-Key": key, "Accept": "*/*"},
                    timeout=20,
                    verify=False,
                )
            except requests.RequestException as exc:
                diagnostics.append(
                    {
                        "api_id": api_id,
                        "endpoint": endpoint,
                        "params": params,
                        "error": str(exc),
                    }
                )
                logger.exception(
                    "Direct Reinfolib request failed request_id=%s api_id=%s endpoint=%s params=%s error=%s",
                    request_id,
                    api_id,
                    endpoint,
                    params,
                    exc,
                )
                continue

            body_prefix = response.text[:300]
            diagnostic = {
                "api_id": api_id,
                "api_name": REINFOLIB_API_NAMES.get(api_id),
                "endpoint": endpoint,
                "params": params,
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type"),
                "body_prefix": body_prefix if not response.ok else "",
            }
            diagnostics.append(diagnostic)
            logger.info(
                "Direct Reinfolib response request_id=%s api_id=%s endpoint=%s status_code=%s content_type=%s params=%s body_prefix=%s",
                request_id,
                api_id,
                endpoint,
                response.status_code,
                response.headers.get("content-type"),
                params,
                body_prefix if not response.ok else "",
            )

            if not response.ok:
                continue

            try:
                data = response.json()
            except ValueError:
                continue

            features = data.get("features") if isinstance(data, dict) else None
            if isinstance(features, list):
                merged_features.extend(features)

        direct_features = filter_direct_features(api_id, merged_features, float(lat), float(lon))
        logger.info(
            "Direct Reinfolib feature summary request_id=%s api_id=%s endpoint=%s raw_feature_count=%s filtered_feature_count=%s",
            request_id,
            api_id,
            endpoint,
            len(merged_features),
            len(direct_features),
        )
        if direct_features:
            feature_collections.append(
                {
                    "type": "FeatureCollection",
                    "features": direct_features,
                    "properties": {
                        "api_id": api_id,
                        "api_name": REINFOLIB_API_NAMES.get(api_id),
                        "source": "direct_reinfolib_fallback",
                    },
                }
            )

    features = []
    for collection in feature_collections:
        features.extend(collection["features"])

    geojson = {"type": "FeatureCollection", "features": features} if features else None
    return geojson, {"tile": tile, "diagnostics": diagnostics, "feature_count": len(features)}


@router.get("/")
def read_root():
    return {"message": "Hello GeoAI"}


@router.get("/health")
def health_check():
    return {"status": "ok", "app": "geoai-app"}


@router.get("/api/mlit/status")
def get_mlit_status():
    return {
        "configured": get_reinfolib_mcp_command() is not None or get_data_platform_mcp_command() is not None,
        "openai_configured": is_openai_configured(),
        "providers": {
            "reinfolib": {
                "configured": get_reinfolib_mcp_command() is not None,
                "api_configured": is_library_api_configured(),
                "api_key_fingerprint": get_library_api_key_fingerprint(),
                "command_env": REINFOLIB_MCP_COMMAND_ENV,
                "tool_env": REINFOLIB_MCP_TOOL_ENV,
            },
            "data_platform": {
                "configured": get_data_platform_mcp_command() is not None,
                "api_configured": is_data_platform_api_configured(),
                "api_key_fingerprint": get_data_platform_api_key_fingerprint(),
                "command_env": MLIT_DATA_PLATFORM_MCP_COMMAND_ENV,
                "tool_env": MLIT_DATA_PLATFORM_MCP_TOOL_ENV,
            },
        },
        "library_api_configured": is_library_api_configured(),
        "data_platform_api_configured": is_data_platform_api_configured(),
        "library_api_env": LIBRARY_API_KEY_ENV,
    }


@router.get("/api/mlit/reinfolib/diagnostics")
def diagnose_reinfolib_api():
    request_id = uuid.uuid4().hex[:12]
    key = os.getenv(LIBRARY_API_KEY_ENV, "")
    fingerprint = get_library_api_key_fingerprint()
    url = "https://www.reinfolib.mlit.go.jp/ex-api/external/XPT002"
    params = {
        "response_format": "geojson",
        "z": 14,
        "x": 14624,
        "y": 6016,
        "year": 2025,
    }

    logger.info(
        "Reinfolib diagnostics started request_id=%s key_fingerprint=%s params=%s",
        request_id,
        fingerprint,
        params,
    )

    if not key:
        logger.warning("Reinfolib diagnostics skipped request_id=%s reason=missing_key", request_id)
        return {
            "request_id": request_id,
            "ok": False,
            "status_code": None,
            "message": f"{LIBRARY_API_KEY_ENV} is not set.",
            "key_fingerprint": fingerprint,
        }

    try:
        response = requests.get(
            url,
            params=params,
            headers={"Ocp-Apim-Subscription-Key": key, "Accept": "*/*"},
            timeout=20,
            verify=False,
        )
    except requests.RequestException as exc:
        logger.exception("Reinfolib diagnostics failed request_id=%s error=%s", request_id, exc)
        return {
            "request_id": request_id,
            "ok": False,
            "status_code": None,
            "message": str(exc),
            "key_fingerprint": fingerprint,
        }

    body_prefix = response.text[:300]
    logger.info(
        "Reinfolib diagnostics completed request_id=%s status_code=%s content_type=%s body_prefix=%s",
        request_id,
        response.status_code,
        response.headers.get("content-type"),
        body_prefix,
    )

    return {
        "request_id": request_id,
        "ok": response.ok,
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type"),
        "body_prefix": body_prefix,
        "key_fingerprint": fingerprint,
    }


@router.get("/api/mlit/data-platform/detail")
def get_data_platform_detail(
    dataset_id: str = Query(..., min_length=1),
    data_id: str = Query(..., min_length=1),
):
    request_id = uuid.uuid4().hex[:12]
    logger.info(
        "Data platform detail received request_id=%s dataset_id=%s data_id=%s data_platform_api_configured=%s",
        request_id,
        dataset_id,
        data_id,
        is_data_platform_api_configured(),
    )

    try:
        detail_response = call_mcp_tool_by_name(
            "data_platform",
            "get_data",
            {"dataset_id": dataset_id, "data_id": data_id},
            request_id,
            "leaflet_popup_detail",
        )
    except Exception as exc:
        logger.exception(
            "Data platform detail failed request_id=%s dataset_id=%s data_id=%s error=%s",
            request_id,
            dataset_id,
            data_id,
            exc,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    detail_text = extract_result_text(detail_response["result"])
    detail_payload = parse_result_payload(detail_text)
    detail = extract_data_platform_detail(detail_payload)
    thumbnails: list[dict[str, str]] = []
    thumbnail_warning = None

    if detail and detail.get("hasThumbnail"):
        try:
            thumbnail_response = call_mcp_tool_by_name(
                "data_platform",
                "get_thumbnail_urls",
                {"dataset_id": dataset_id, "data_id": data_id},
                request_id,
                "leaflet_popup_thumbnail",
            )
            thumbnail_text = extract_result_text(thumbnail_response["result"])
            thumbnails = extract_thumbnail_urls(parse_result_payload(thumbnail_text))
            if not thumbnails:
                thumbnail_warning = "サムネイルありのデータですが、URLは返りませんでした。"
        except Exception as exc:
            thumbnail_warning = str(exc)
            logger.exception(
                "Data platform thumbnail failed request_id=%s dataset_id=%s data_id=%s error=%s",
                request_id,
                dataset_id,
                data_id,
                exc,
            )

    logger.info(
        "Data platform detail completed request_id=%s dataset_id=%s data_id=%s detail_found=%s has_thumbnail=%s thumbnail_count=%s thumbnail_warning=%s",
        request_id,
        dataset_id,
        data_id,
        detail is not None,
        detail.get("hasThumbnail") if isinstance(detail, dict) else None,
        len(thumbnails),
        thumbnail_warning,
    )

    return {
        "request_id": request_id,
        "dataset_id": dataset_id,
        "data_id": data_id,
        "detail": detail,
        "thumbnails": thumbnails,
        "thumbnail_warning": thumbnail_warning,
    }


@router.post("/api/mlit/query")
def query_mlit_data(payload: MlitQuery):
    request_id = uuid.uuid4().hex[:12]
    query = payload.query.strip()
    if not query:
        logger.warning("MLIT query rejected request_id=%s reason=empty_query", request_id)
        raise HTTPException(status_code=400, detail="Query is required.")

    logger.info(
        "MLIT query received request_id=%s query=%s reinfolib_mcp_configured=%s data_platform_mcp_configured=%s openai_configured=%s library_api_configured=%s data_platform_api_configured=%s",
        request_id,
        query,
        get_reinfolib_mcp_command() is not None,
        get_data_platform_mcp_command() is not None,
        is_openai_configured(),
        is_library_api_configured(),
        is_data_platform_api_configured(),
    )

    try:
        mcp_response = call_mlit_mcp(query, request_id=request_id)
    except Exception as exc:
        logger.exception("MLIT query failed request_id=%s error=%s", request_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    result = mcp_response["result"]
    geojson = find_geojson(result)
    diagnostics = mcp_response.get("diagnostics") or ""
    text = extract_result_text(result)
    result_payload = parse_result_payload(text)
    api_result_summary = summarize_api_results(result_payload)
    warning = None
    direct_reinfolib_diagnostics = None
    if isinstance(result, dict) and result.get("isError"):
        warning = f"{mcp_response.get('provider')} MCPツールがエラーを返しました: {text[:300]}"

    if not geojson and mcp_response.get("provider") == "data_platform":
        geojson = geojson_from_data_platform_payload(result_payload)
        total = data_platform_result_count(result_payload)
        if not geojson and total == 0:
            warning = "国土交通データプラットフォーム検索は成功しましたが、条件に一致するデータは0件でした。検索語や半径を広げてください。"

    if not geojson and mcp_response.get("provider") == "reinfolib" and is_library_api_configured():
        direct_geojson, direct_reinfolib_diagnostics = fetch_direct_reinfolib_geojson(
            mcp_response["arguments"],
            request_id,
        )
        if direct_geojson:
            geojson = direct_geojson
            warning = "MCPレスポンスは空でしたが、不動産情報ライブラリAPIを直接再取得して地図に表示しました。"

    if not geojson and warning is None and mcp_response.get("provider") == "reinfolib":
        direct_statuses = [
            item.get("status_code")
            for item in (direct_reinfolib_diagnostics or {}).get("diagnostics", [])
            if isinstance(item, dict)
        ]
        if 401 in direct_statuses or "401 Client Error: Access Denied" in diagnostics:
            warning = (
                "不動産情報ライブラリAPIが401 Access Deniedを返しました。"
                " コンテナが読んでいるLIBRARY_API_KEYがAPIキー発行画面の値と一致しているか、"
                "または当該APIを利用できる有効なサブスクリプションキーか確認してください。"
            )
        elif not is_library_api_configured():
            warning = f"{LIBRARY_API_KEY_ENV} が未設定のため、国土交通省APIの実データを取得できません。"
        elif has_only_empty_api_results(result_payload):
            warning = (
                "国土交通省APIから地図表示用データが返りませんでした。"
                " 条件に該当するデータがないか、LIBRARY_API_KEYの有効性・権限に問題がある可能性があります。"
            )

    logger.info(
        "MLIT query completed request_id=%s tool=%s geojson_found=%s warning=%s arguments=%s api_result_summary=%s direct_reinfolib_diagnostics=%s",
        request_id,
        mcp_response["tool"],
        geojson is not None,
        warning,
        mcp_response["arguments"],
        api_result_summary,
        direct_reinfolib_diagnostics,
    )

    return {
        "request_id": request_id,
        "query": query,
        "provider": mcp_response.get("provider"),
        "tool": mcp_response["tool"],
        "arguments": mcp_response["arguments"],
        "planner": mcp_response.get("planner"),
        "geojson": geojson,
        "warning": warning,
        "direct_reinfolib_diagnostics": direct_reinfolib_diagnostics,
        "text": text,
        "raw": result,
    }
