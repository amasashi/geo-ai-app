from request_processor.service.apis.base_api import BasePolygonApi
from utils.const import LIBRARY_API_URL


class RealEstateApi19(BasePolygonApi):
    API_CONFIG = {
        "name": "国土数値情報（自然公園地域）",
        "path": f"{LIBRARY_API_URL}/XKT019",
        "response_type": "geojson",
    }

    def _build_params(self):
        params = super()._build_params()
        # 任意のパラメータ
        optional_param_mapping = {
            "prefectureCode": "prefecture_code",
            "districtCode": "district_code",
        }
        for api_key, req_key in optional_param_mapping.items():
            value = self.req_body.get(req_key)
            if value is not None:
                params[api_key] = (
                    ",".join(str(v).lstrip("0") for v in value)
                    if isinstance(value, list)
                    else str(value).lstrip("0")
                )
        return params
