from request_processor.service.apis.base_api import BasePolygonApi
from utils.const import LIBRARY_API_URL


class RealEstateApi25(BasePolygonApi):
    API_CONFIG = {
        "name": "国土交通省都市局（地形区分に基づく液状化の発生傾向図）",
        "path": f"{LIBRARY_API_URL}/XKT025",
        "response_type": "geojson",
    }
