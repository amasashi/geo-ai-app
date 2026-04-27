from request_processor.common import requester
from request_processor.common.change_address import (
    get_cityname,
    get_district_name,
    get_pref_name,
)
from request_processor.service.apis.base_api import BaseRealEstateApi
from utils.const import LIBRARY_API_KEY, LIBRARY_API_URL
from utils.geocoder import get_latlon


class RealEstateApi1(BaseRealEstateApi):
    API_CONFIG = {
        "name": "不動産取引価格（取引価格・成約価格）情報",
        "path": f"{LIBRARY_API_URL}/XIT001",
        "response_type": "json",
    }

    def _call_api(self):
        # パラメータ生成
        headers = {
            "Ocp-Apim-Subscription-Key": f"{LIBRARY_API_KEY}",
            "Accept": "*/*",
        }
        params = {
            "year": self.req_body.get("year"),
            "city": self.converted["muni_cd"],
        }

        # 任意のパラメータを外部APIへのリクエストにセットする
        optional_param_mapping = {
            "priceClassification": "price_classification",
            "quarter": "quarter",
            "language": "language",
        }
        for api_key, req_key in optional_param_mapping.items():
            value = self.req_body.get(req_key)
            if value is not None:
                params[api_key] = value

        # 外部API呼び出し
        response = requester.get(
            url=self.API_CONFIG["path"],
            params=params,
            response_type=self.API_CONFIG["response_type"],
            headers=headers,
        )

        return response

    def _process_data(self, data):
        try:
            if not data or "data" not in data:
                self.logger.info("APIから有効なデータが取得できませんでした。")
                return None

            # 絞り込み処理
            # 住所（大字レベル）取得
            prefecture = get_pref_name(self.converted["muni_cd"])
            municipality = get_cityname(self.converted["muni_cd"])
            district_name = get_district_name(self.converted["lv_01_nm"])
            full_addr = f"{prefecture}{municipality}{district_name}"

            # 検索座標と同じ地名のデータを取得
            filter_data = [
                item
                for item in data["data"]
                if item.get("Prefecture") == prefecture
                and item.get("Municipality") == municipality
                and item.get("DistrictName") == district_name
            ]

            if not filter_data:
                self.logger.info("該当データなし")
                return None

            # ジオコーダで緯度経度を取得
            coordinates = get_latlon(full_addr)
            if coordinates is None or None in coordinates:
                self.logger.error(
                    f"不動産取引価格（取引価格・成約価格）情報のジオコーダ失敗: {full_addr}"
                )
                return None

            # GeoJSON形式に変換＋緯度経度追加
            features = [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": coordinates},
                    "properties": item,
                }
                for item in filter_data
            ]
            geojson = {"type": "FeatureCollection", "features": features}

        except Exception as e:
            self.logger.error(
                f"不動産取引価格（取引価格・成約価格）情報 excange エラー:{e}"
            )  # エラーは基底クラスで捕捉される
            raise  # 再スローして基底クラスに処理を委ねる

        return geojson
