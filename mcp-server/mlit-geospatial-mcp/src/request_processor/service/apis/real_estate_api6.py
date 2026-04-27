from request_processor.service.apis.base_api import BasePolygonApi
from utils.const import LIBRARY_API_URL


class RealEstateApi6(BasePolygonApi):
    API_CONFIG = {
        "name": "都市計画決定GISデータ（立地適正化計画）",
        "path": f"{LIBRARY_API_URL}/XKT003",
        "response_type": "geojson",
    }
