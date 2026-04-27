import requests

from utils.const import RGEOCODER_URL


# 住所から緯度経度(国土地理院のジオコーダ)
def get_latlon(full_addr):
    response = requests.get(
        f"{RGEOCODER_URL}?q={full_addr}",
        headers={"User-Agent": "REINS-Client"},
        verify=False,
    )

    result = response.json()

    if result and isinstance(result, list) and len(result) > 0:
        lon = result[0]["geometry"]["coordinates"][0]
        lat = result[0]["geometry"]["coordinates"][1]
        coordinates = [lon, lat]
        return coordinates
    else:
        return [None, None]
