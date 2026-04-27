from request_processor.service.apis.base_api import BasePointApi
from utils.const import LIBRARY_API_URL


class RealEstateApi18(BasePointApi):
    API_CONFIG = {
        "name": "国土数値情報（市区町村役場及び集会施設等）",
        "path": f"{LIBRARY_API_URL}/XKT018",
        "response_type": "geojson",
    }
