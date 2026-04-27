from request_processor.common import requester
from request_processor.common.point_filter import filter_distance
from request_processor.service.apis.base_api import BaseRealEstateApi
from utils.const import LIBRARY_API_KEY, LIBRARY_API_URL


class RealEstateApi2(BaseRealEstateApi):
    API_CONFIG = {
        "name": "鑑定評価書情報",
        "path": f"{LIBRARY_API_URL}/XCT001",
        "response_type": "json",
    }

    def _call_api(self):
        # division分を回していく
        divisions = self.req_body.get("division", [None])
        results = {"data": []}
        # 都道府県CD
        muni_cd = self.converted["muni_cd"]
        area = muni_cd[:2]

        for div in divisions:
            # パラメータ生成
            headers = {
                "Ocp-Apim-Subscription-Key": f"{LIBRARY_API_KEY}",
                "Accept": "*/*",
            }
            params = {
                "year": self.req_body.get("year"),
                "area": area,
                "division": div,
            }

            # 外部API呼び出し
            try:
                response = requester.get(
                    url=self.API_CONFIG["path"],
                    params=params,
                    response_type=self.API_CONFIG["response_type"],
                    headers=headers,
                )
                # "data"キーがあり、中身がリストであることを確認
                data = response.get("data")
                if not data or not isinstance(data, list):
                    continue
                results["data"].extend(data)
            except Exception as e:
                self.logger.error(f"鑑定評価書情報API 呼び出し失敗:{e}")

        return results

    def _process_data(self, data):
        try:
            # APIから有効なデータが取得できなかった、またはdataキーがない、またはdataが空リストの場合
            if not data or "data" not in data or not data["data"]:
                self.logger.info("APIから有効なデータが取得できませんでした。")
                return None

            # json→geojsonへ変換、座標情報付与
            features = [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [
                            float(item["位置座標 経度"]),
                            float(item["位置座標 緯度"]),
                        ],
                    },
                    "properties": item,
                }
                for item in data["data"]
            ]

            # 距離での絞り込み
            distance = self.req_body.get("distance")
            filtered_features = filter_distance(
                features=features,
                latlon=(self.converted["lat"], self.converted["lon"]),
                distance=distance,
            )
            if not filtered_features:
                self.logger.info(
                    "鑑定評価書情報APIの該当データなし（距離での絞り込み後）"
                )
                return None

            geojson = {"type": "FeatureCollection", "features": filtered_features}
            return geojson

        except Exception as e:
            self.logger.error(f"鑑定評価書情報API excange エラー:{e}")
            raise
