from request_processor.service.apis.base_api import BasePolygonApi
from utils.const import LIBRARY_API_URL


class RealEstateApi20(BasePolygonApi):
    API_CONFIG = {
        "name": "国土数値情報（大規模盛土造成地マップ）",
        "path": f"{LIBRARY_API_URL}/XKT020",
        "response_type": "geojson",
    }
