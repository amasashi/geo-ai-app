from request_processor.service.apis.base_api import BasePolygonApi
from utils.const import LIBRARY_API_URL


class RealEstateApi14(BasePolygonApi):
    API_CONFIG = {
        "name": "都市計画決定GISデータ（防火・準防火地域）",
        "path": f"{LIBRARY_API_URL}/XKT014",
        "response_type": "geojson",
    }
