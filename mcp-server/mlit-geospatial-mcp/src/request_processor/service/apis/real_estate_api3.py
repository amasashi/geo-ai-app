from request_processor.common import requester
from request_processor.common.point_filter import filter_distance, get_surrounding_tiles
from utils.const import LIBRARY_API_KEY, LIBRARY_API_URL, ZOOM
from utils.logger_config import setup_logger


class RealEstateApi3:
    API_CONFIG = {
        "name": "地価公示・地価調査のポイント（点）",
        "path": f"{LIBRARY_API_URL}/XPT002",
        "response_type": "geojson",
    }

    def __init__(self, req_body: dict, converted: dict):
        # ラムダから渡されたリクエストデータ
        self.req_body = req_body
        # 座標変換済データ
        self.converted = converted
        self.logger = setup_logger(__name__)

    def _call_get_api(self):
        # 4タイル分取得
        tiles = get_surrounding_tiles(
            self.converted["x"],
            self.converted["y"],
            self.converted["x_frac"],
            self.converted["y_frac"],
        )

        merged_geojson = {"type": "FeatureCollection", "features": []}

        for x, y in tiles:
            self.logger.info(f"ｘ：{x},y:{y}")
            # パラメータ生成
            headers = {
                "Ocp-Apim-Subscription-Key": f"{LIBRARY_API_KEY}",
                "Accept": "*/*",
            }
            params = {
                "response_format": "geojson",
                "z": ZOOM,
                "x": x,
                "y": y,
                "year": self.req_body.get("year"),
            }
            # 任意のパラメータ
            optional_param_mapping = {
                "priceClassification": "land_price_classification",
                "useCategoryCode": "use_category_code",
            }

            for api_key, req_key in optional_param_mapping.items():
                value = self.req_body.get(req_key)
                if value is not None:
                    if isinstance(value, list):
                        # リストをカンマ区切りの文字列に変換
                        params[api_key] = ",".join(map(str, value))
                    else:
                        params[api_key] = value

            # 外部API呼び出し
            try:
                response = requester.get(
                    url=self.API_CONFIG["path"],
                    params=params,
                    response_type=self.API_CONFIG["response_type"],
                    headers=headers,
                )
                if not response or not isinstance(response, dict):
                    continue

                features = response.get("features")
                if not features:
                    continue

                merged_geojson["features"].extend(features)

            except Exception as e:
                self.logger.error(
                    f"地価公示・地価調査のポイント（点） 呼び出し失敗:{e}"
                )

        return merged_geojson

    def exchange(self):
        self.logger.info("地価公示・地価調査のポイント（点） excange開始")
        try:
            # 外部APIにリクエストする
            data = self._call_get_api()

            # APIから有効なデータが取得できなかった場合
            if not data or not data.get("features"):
                self.logger.info("地価公示・地価調査のポイント（点）の該当データなし")
                return None

            # パラメータできた半径距離内にある情報を取得
            distance = self.req_body.get("distance")

            # 距離による絞り込み
            filtered_features = filter_distance(
                features=data["features"],
                latlon=(self.converted["lat"], self.converted["lon"]),
                distance=distance,
            )
            if not filtered_features:
                self.logger.info("地価公示・地価調査のポイント（点）の該当データなし")
                return None

            data["features"] = filtered_features

        except Exception as e:
            self.logger.error(f"地価公示・地価調査のポイント（点） excange エラー:{e}")
            return None

        return {
            "file_name": "地価公示・地価調査のポイント（点）.geojson",
            "data": data,
        }
