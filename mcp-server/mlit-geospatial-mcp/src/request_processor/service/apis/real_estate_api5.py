from request_processor.service.apis.base_api import BasePolygonApi
from utils.const import LIBRARY_API_URL


class RealEstateApi5(BasePolygonApi):
    API_CONFIG = {
        "name": "都市計画決定GISデータ（用途地域）",
        "path": f"{LIBRARY_API_URL}/XKT002",
        "response_type": "geojson",
    }
