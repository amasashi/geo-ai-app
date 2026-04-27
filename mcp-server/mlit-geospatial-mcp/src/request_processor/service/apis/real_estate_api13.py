from request_processor.service.apis.base_api import BasePolygonApi
from utils.const import LIBRARY_API_URL


class RealEstateApi13(BasePolygonApi):
    API_CONFIG = {
        "name": "国土数値情報（将来推計人口250mメッシュ）",
        "path": f"{LIBRARY_API_URL}/XKT013",
        "response_type": "geojson",
    }
