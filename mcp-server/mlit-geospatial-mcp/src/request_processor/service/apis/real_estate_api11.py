from request_processor.service.apis.base_api import BasePointApi
from utils.const import LIBRARY_API_URL


class RealEstateApi11(BasePointApi):
    API_CONFIG = {
        "name": "国土数値情報（医療機関）",
        "path": f"{LIBRARY_API_URL}/XKT010",
        "response_type": "geojson",
    }
