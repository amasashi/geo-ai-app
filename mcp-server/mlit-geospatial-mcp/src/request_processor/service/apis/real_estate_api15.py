from request_processor.service.apis.base_api import BasePointApi
from utils.const import LIBRARY_API_URL


class RealEstateApi15(BasePointApi):
    API_CONFIG = {
        "name": "国土数値情報（駅別乗降客数）",
        "path": f"{LIBRARY_API_URL}/XKT015",
        "response_type": "geojson",
    }
