from request_processor.service.apis.base_api import BasePointApi
from utils.const import LIBRARY_API_URL


class RealEstateApi10(BasePointApi):
    API_CONFIG = {
        "name": "国土数値情報（保育園・幼稚園等）",
        "path": f"{LIBRARY_API_URL}/XKT007",
        "response_type": "geojson",
    }
