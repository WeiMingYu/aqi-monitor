"""
api/routes/cities.py - 城市清單 API 路由
提供監控城市清單及最新 AQI 摘要
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime

from core.db_init import get_conn

router = APIRouter()


# ===== GET /api/cities =====
@router.get("/cities", summary="取得所有監控城市清單")
def get_cities():
    """
    回傳 watch_list 中所有城市，含最新一筆 AQI 資料。

    回傳格式：
    ```json
    {
      "count": 5,
      "cities": [
        {
          "city_key": "@1591",
          "display_name": "Banqiao, Taiwan（板橋）",
          "geo_lat": 25.01,
          "geo_lon": 121.45,
          "alert_threshold": 100,
          "aqi": 55,
          "pm25": 22.3,
          "aqi_level": "普通",
          "aqi_color": "#FFFF00",
          "fetch_time": "2026-05-09 14:30:00"
        }
      ],
      "timestamp": "2026-05-09 14:35:00"
    }
    ```
    """
    from core.api_client import aqi_level

    conn = get_conn()
    rows = conn.execute("""
        SELECT w.city_key, w.display_name, w.geo_lat, w.geo_lon,
               w.alert_threshold, w.group_name,
               h.aqi, h.pm25, h.pm10, h.fetch_time
        FROM watch_list w
        LEFT JOIN (
            SELECT city_key, aqi, pm25, pm10, fetch_time,
                   ROW_NUMBER() OVER (PARTITION BY city_key ORDER BY fetch_time DESC) rn
            FROM aqi_history
        ) h ON w.city_key = h.city_key AND h.rn = 1
        WHERE w.is_active = 1
        ORDER BY w.id
    """).fetchall()
    conn.close()

    cities = []
    for r in rows:
        lv, color, emoji = aqi_level(r["aqi"])
        cities.append({
            "city_key":        r["city_key"],
            "display_name":    r["display_name"],
            "geo_lat":         r["geo_lat"],
            "geo_lon":         r["geo_lon"],
            "group_name":      r["group_name"],
            "alert_threshold": r["alert_threshold"],
            "aqi":             r["aqi"],
            "pm25":            r["pm25"],
            "pm10":            r["pm10"],
            "aqi_level":       lv,
            "aqi_color":       color,
            "aqi_emoji":       emoji,
            "fetch_time":      r["fetch_time"],
        })

    return {
        "count":     len(cities),
        "cities":    cities,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ===== GET /api/cities/{city_key} =====
@router.get("/cities/{city_key}", summary="取得單一城市資訊")
def get_city(city_key: str):
    """
    取得指定城市的詳細資訊。
    city_key 格式：@1591（需 URL encode，如 %401591）
    """
    conn = get_conn()
    row  = conn.execute(
        "SELECT * FROM watch_list WHERE city_key = ?", (city_key,)
    ).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"城市 {city_key} 不在監控清單中")

    return {
        "city_key":        row["city_key"],
        "display_name":    row["display_name"],
        "geo_lat":         row["geo_lat"],
        "geo_lon":         row["geo_lon"],
        "group_name":      row["group_name"],
        "alert_threshold": row["alert_threshold"],
        "is_active":       row["is_active"],
        "created_at":      row["created_at"],
    }
