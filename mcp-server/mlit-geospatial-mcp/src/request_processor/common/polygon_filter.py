from typing import Dict, List, Tuple

from shapely import wkt as _wkt
from shapely.geometry import MultiPolygon, Polygon

from utils.logger_config import setup_logger

# 重なり判定
logger = setup_logger(__name__)


# 不動産ライブラリのポリゴン重なり判定
def overlap_judge(features: List[Dict], latlon: Tuple[float, float]) -> List[Dict]:
    search_lat, search_lon = latlon
    search_geom = f"POINT({search_lon} {search_lat})"
    filtered = []

    for feature in features:
        # geojsonの座標情報

        geom = feature.get("geometry", {})
        multipolygon = geojson_coords_to_multipolygon_wkt(geom)

        result = judge_intersects(search_geom, multipolygon)

        if result:
            filtered.append(feature)

    return filtered


def geojson_coords_to_multipolygon_wkt(geometry: Dict) -> str:
    try:
        geom_type = geometry.get("type")
        coordinates = geometry.get("coordinates", [])

        if geom_type == "Polygon":
            polygon = Polygon(coordinates[0])
            multipolygon = MultiPolygon([polygon])
        elif geom_type == "MultiPolygon":
            polygons = []
            for poly_coords in coordinates:
                polygon = Polygon(poly_coords[0])  # 外周リングのみ使用
                polygons.append(polygon)
            multipolygon = MultiPolygon(polygons)
        else:
            logger.error(f"未対応のgeometry type: {geom_type}")
            return None

        return multipolygon.wkt
    except Exception as e:
        logger.error(f"GeoJSON座標の変換エラー: {e}")
        return None


# 部分一致
def judge_intersects(geom1: str, geom2: str) -> bool:
    try:
        g1 = _wkt.loads(geom1)
        g2 = _wkt.loads(geom2)
        return g1.intersects(g2)
    except Exception:
        return False
