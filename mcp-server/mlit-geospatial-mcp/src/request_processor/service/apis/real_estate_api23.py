from request_processor.service.apis.base_api import BasePolygonApi
from utils.const import LIBRARY_API_URL


class RealEstateApi23(BasePolygonApi):
    API_CONFIG = {
        "name": "都市計画決定GISデータ（地区計画）",
        "path": f"{LIBRARY_API_URL}/XKT023",
        "response_type": "geojson",
    }
