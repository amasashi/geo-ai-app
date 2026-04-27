from request_processor.service.apis.base_api import BasePointApi
from utils.const import LIBRARY_API_URL


class RealEstateApi9(BasePointApi):
    API_CONFIG = {
        "name": "国土数値情報（学校）",
        "path": f"{LIBRARY_API_URL}/XKT006",
        "response_type": "geojson",
    }
