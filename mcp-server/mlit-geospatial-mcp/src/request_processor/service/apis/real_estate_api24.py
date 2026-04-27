from request_processor.service.apis.base_api import BasePolygonApi
from utils.const import LIBRARY_API_URL


class RealEstateApi24(BasePolygonApi):
    API_CONFIG = {
        "name": "都市計画決定GISデータ（高度利用地区）",
        "path": f"{LIBRARY_API_URL}/XKT024",
        "response_type": "geojson",
    }
