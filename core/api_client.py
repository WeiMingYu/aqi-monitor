"""
core/api_client.py - WAQI API 封裝模組
所有對外 API 呼叫集中於此，統一回傳 {"ok": bool, ...} 格式
"""

import requests
import os
from dotenv import load_dotenv

# ===== 1. 載入 .env（從專案根目錄）=====
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_BASE_DIR, ".env"))

WAQI_TOKEN = os.getenv("WAQI_TOKEN", "demo")
BASE_URL   = "https://api.waqi.info"


# ===== 2. 城市查詢 =====

def fetch_by_city(city_key: str) -> dict:
    """
    依城市名稱或站台ID查詢即時 AQI
    city_key: 城市名如 "taipei"，或站台ID如 "@7397"
    """
    url = f"{BASE_URL}/feed/{city_key}/?token={WAQI_TOKEN}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        if result.get("status") == "ok":
            return {"ok": True, "data": _parse_station(result["data"], city_key)}
        else:
            return {"ok": False, "error": result.get("data", "API 回傳錯誤")}
    except requests.exceptions.Timeout:
        return {"ok": False, "error": "連線逾時，請稍後再試"}
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": str(e)}


def fetch_by_geo(lat: float, lon: float) -> dict:
    """依 GPS 座標查詢最近監測站"""
    url = f"{BASE_URL}/feed/geo:{lat};{lon}/?token={WAQI_TOKEN}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        if result.get("status") == "ok":
            return {"ok": True, "data": _parse_station(result["data"], f"geo:{lat},{lon}")}
        else:
            return {"ok": False, "error": result.get("data", "查無附近監測站")}
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": str(e)}


def search_stations(keyword: str) -> dict:
    """
    搜尋符合關鍵字的監測站清單
    注意：API 回傳的 aqi 是字串（可能是 "-" 或數字字串），需做型別轉換
    city_key 優先使用 station.url（如 taiwan/taipei/zhongshan），其次用 @uid
    """
    url = f"{BASE_URL}/search/?token={WAQI_TOKEN}&keyword={keyword}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        if result.get("status") == "ok":
            stations = []
            for s in result.get("data", []):
                # ===== aqi 可能是字串 "-" 或 "42"，統一轉成數字或保留 "-" =====
                raw_aqi = s.get("aqi", "-")
                try:
                    aqi_val = int(float(str(raw_aqi)))
                except (ValueError, TypeError):
                    aqi_val = "-"   # 無效值保留為字串

                # ===== city_key：永遠用 @uid，這是 API 唯一可靠的查詢格式 =====
                # station.url（如 taiwan/taipei/zhongshan）只用於顯示，不用於查詢
                station_url = s.get("station", {}).get("url", "")
                uid         = s.get("uid")
                city_key    = f"@{uid}" if uid else ""

                stations.append({
                    "uid":      uid,
                    "name":     s.get("station", {}).get("name", ""),
                    "aqi":      aqi_val,
                    "geo":      s.get("station", {}).get("geo", [None, None]),
                    "url":      station_url,    # 顯示用（如 taiwan/taipei/zhongshan）
                    "city_key": city_key,       # 查詢用（直接傳給 fetch_by_city）
                })
            return {"ok": True, "stations": stations}
        else:
            return {"ok": False, "error": "搜尋無結果"}
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": str(e)}


# ===== 3. 資料解析 =====

def _parse_station(data: dict, city_key: str) -> dict:
    """
    將 WAQI API 原始 data 整理成統一格式
    注意：forecast 中 PM10 的 key 是 pmp10（非 pm10），這是 API 設計的不一致點
    """
    iaqi = data.get("iaqi", {})

    def safe_get(key):
        """安全取 iaqi 中的數值，不存在回傳 None"""
        val = iaqi.get(key, {}).get("v")
        try:
            return float(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    # ===== 解析預報資料 =====
    forecast_daily  = data.get("forecast", {}).get("daily", {})
    forecast_parsed = {}
    for pollutant, records in forecast_daily.items():
        if not isinstance(records, list):
            continue
        forecast_parsed[pollutant] = [
            {
                "day": r.get("day"),
                "avg": r.get("avg"),
                "max": r.get("max"),
                "min": r.get("min"),
            }
            for r in records if r.get("day")
        ]

    # ===== 解析資料來源歸因 =====
    attributions = [
        {"name": a.get("name", ""), "url": a.get("url", "")}
        for a in data.get("attributions", [])
    ]

    return {
        "city_key":      city_key,
        "station_idx":   data.get("idx"),
        "station_name":  data.get("city", {}).get("name", city_key),
        "station_url":   data.get("city", {}).get("url", ""),
        "geo":           data.get("city", {}).get("geo", [None, None]),
        "aqi":           data.get("aqi"),
        "measure_time":  data.get("time", {}).get("s"),
        "tz":            data.get("time", {}).get("tz"),
        # ===== iaqi 即時污染物 =====
        "pm25":     safe_get("pm25"),
        "pm10":     safe_get("pm10"),   # iaqi 裡用 pm10
        "no2":      safe_get("no2"),
        "co":       safe_get("co"),
        "so2":      safe_get("so2"),
        "o3":       safe_get("o3"),
        "temp":     safe_get("t"),
        "humidity": safe_get("h"),
        "wind":     safe_get("w"),
        # ===== 預報（forecast.daily 裡 PM10 用 pmp10）=====
        "forecast":      forecast_parsed,
        "forecast_pm10": forecast_parsed.get("pmp10", []),   # 別名，方便存取
        "forecast_uvi":  forecast_parsed.get("uvi", []),
        # ===== 資料來源 =====
        "attributions":  attributions,
    }


# ===== 4. AQI 等級判斷 =====

def aqi_level(aqi_val) -> tuple:
    """
    依 AQI 數值回傳 (等級文字, 顏色代碼, emoji)
    參考美國 EPA 標準
    """
    try:
        v = int(aqi_val)
    except (TypeError, ValueError):
        return ("未知", "#999999", "❓")

    if v <= 50:   return ("優良",              "#00E400", "🟢")
    if v <= 100:  return ("普通",              "#FFFF00", "🟡")
    if v <= 150:  return ("對敏感族群不健康",  "#FF7E00", "🟠")
    if v <= 200:  return ("不健康",            "#FF0000", "🔴")
    if v <= 300:  return ("非常不健康",        "#8F3F97", "🟣")
    return             ("危險",               "#7E0023", "⚫")
