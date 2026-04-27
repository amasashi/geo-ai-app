"""
座標変換ユーティリティモジュール。

このモジュールは、緯度経度をタイル座標やメッシュコードに変換する関数を提供。

Functions:
    latlon_to_tile_fraction(lat: float, lon: float, zoom: int) -> tuple[int, int, float, float]:
        緯度経度をタイル座標（整数）とタイル内の相対位置（小数）に変換。

    latlon_to_address(lat: float, lon: float) -> tuple[str, str]:
        緯度経度から市区町村コードと名称を取得。
"""

from math import cos, floor, log, pi, radians, tan

from utils import reverse_geocoder


# タイル内の相対位置を取得
def latlon_to_tile_fraction(lat: float, lon: float, zoom: int):
    """
    緯度経度をタイル座標とタイル内の相対位置に変換。
    周辺タイル情報の取得時に活用。

    Args:
        lat (float): 緯度
        lon (float): 経度
        zoom (int): ズームレベル

    Returns:
        tuple[int, int, float, float]: タイル座標 (x, y) とタイル内の相対位置 (x_frac, y_frac)
    """

    # どのタイルに属するか計算（小数点込）
    n = 2**zoom
    lat_rad = radians(lat)
    x_float = n * ((lon + 180) / 360)
    y_float = n * (1 - (log(tan(lat_rad) + 1 / cos(lat_rad)) / pi)) / 2

    # 整数
    x = floor(x_float)
    y = floor(y_float)

    # タイル内での相対位置（小数点部分）
    x_frac = x_float - x
    y_frac = y_float - y

    return x, y, x_frac, y_frac


# 住所変換
def latlon_to_address(lat: float, lon: float) -> dict:
    """
    緯度経度から市区町村コードと町丁目レベルの住所を取得。

    Args:
        lat (float): 緯度
        lon (float): 経度

    Returns:
        tuple[str, str]: 市区町村コードと町丁目レベルの住所（例：本町一丁目）。
    """

    muni_cd, lv_01_nm = reverse_geocoder.get_citycd(lat, lon)
    return muni_cd, lv_01_nm
