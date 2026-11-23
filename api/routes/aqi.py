"""
api/routes/aqi.py - AQI 資料 API 路由
提供即時 AQI、歷史資料、預報資料
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime, timedelta

from core.db_init import get_conn

router = APIRouter()


# ===== GET /api/aqi/all =====
@router.get("/aqi/all", summary="取得所有城市最新 AQI")
def get_all_aqi():
    """
    取得監控清單中所有城市的最新一筆 AQI 資料。
    適合官網 widget 嵌入使用。
    """
    from core.api_client import aqi_level

    conn = get_conn()
    rows = conn.execute("""
        SELECT w.city_key, w.display_name, w.geo_lat, w.geo_lon,
               h.aqi, h.pm25, h.pm10, h.no2, h.o3,
               h.temp, h.humidity, h.wind,
               h.measure_time, h.fetch_time
        FROM watch_list w
        LEFT JOIN (
            SELECT city_key, aqi, pm25, pm10, no2, o3,
                   temp, humidity, wind, measure_time, fetch_time,
                   ROW_NUMBER() OVER (PARTITION BY city_key ORDER BY fetch_time DESC) rn
            FROM aqi_history
        ) h ON w.city_key = h.city_key AND h.rn = 1
        WHERE w.is_active = 1
        ORDER BY h.aqi DESC
    """).fetchall()
    conn.close()

    data = []
    for r in rows:
        lv, color, emoji = aqi_level(r["aqi"])
        data.append({
            "city_key":     r["city_key"],
            "display_name": r["display_name"],
            "geo_lat":      r["geo_lat"],
            "geo_lon":      r["geo_lon"],
            "aqi":          r["aqi"],
            "pm25":         r["pm25"],
            "pm10":         r["pm10"],
            "no2":          r["no2"],
            "o3":           r["o3"],
            "temp":         r["temp"],
            "humidity":     r["humidity"],
            "wind":         r["wind"],
            "aqi_level":    lv,
            "aqi_color":    color,
            "aqi_emoji":    emoji,
            "measure_time": r["measure_time"],
            "fetch_time":   r["fetch_time"],
        })

    return {
        "count":     len(data),
        "data":      data,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ===== GET /api/aqi/{city_key} =====
@router.get("/aqi/{city_key}", summary="取得指定城市最新 AQI")
def get_city_aqi(city_key: str):
    """
    取得指定城市最新一筆 AQI 完整資料。
    city_key 格式：@1591
    """
    from core.api_client import aqi_level

    conn = get_conn()
    row  = conn.execute("""
        SELECT h.*, w.display_name, w.geo_lat, w.geo_lon, w.alert_threshold
        FROM aqi_history h
        JOIN watch_list w ON h.city_key = w.city_key
        WHERE h.city_key = ?
        ORDER BY h.fetch_time DESC
        LIMIT 1
    """, (city_key,)).fetchone()
    conn.close()

    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"城市 {city_key} 無資料，請確認已加入監控清單且排程已執行"
        )

    lv, color, emoji = aqi_level(row["aqi"])

    return {
        "city_key":        row["city_key"],
        "display_name":    row["display_name"],
        "geo_lat":         row["geo_lat"],
        "geo_lon":         row["geo_lon"],
        "alert_threshold": row["alert_threshold"],
        "aqi":             row["aqi"],
        "aqi_level":       lv,
        "aqi_color":       color,
        "aqi_emoji":       emoji,
        "pm25":            row["pm25"],
        "pm10":            row["pm10"],
        "no2":             row["no2"],
        "co":              row["co"],
        "so2":             row["so2"],
        "o3":              row["o3"],
        "temp":            row["temp"],
        "humidity":        row["humidity"],
        "wind":            row["wind"],
        "pressure":        row["pressure"],
        "measure_time":    row["measure_time"],
        "fetch_time":      row["fetch_time"],
    }


# ===== GET /api/history/{city_key} =====
@router.get("/history/{city_key}", summary="取得指定城市歷史資料")
def get_history(
    city_key: str,
    days: int = Query(default=7,  ge=1, le=90,  description="查詢天數（1-90）"),
    limit: int = Query(default=200, ge=1, le=1000, description="最大回傳筆數"),
):
    """
    取得指定城市的 AQI 歷史資料。

    參數：
    - **days**：查詢最近幾天（預設 7，最多 90）
    - **limit**：最大回傳筆數（預設 200，最多 1000）
    """
    date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    conn = get_conn()

    # 確認城市存在
    city = conn.execute(
        "SELECT display_name FROM watch_list WHERE city_key = ?", (city_key,)
    ).fetchone()

    if not city:
        conn.close()
        raise HTTPException(status_code=404, detail=f"城市 {city_key} 不在監控清單中")

    rows = conn.execute("""
        SELECT fetch_time, aqi, pm25, pm10, no2, co, so2, o3,
               temp, humidity, wind, pressure, measure_time
        FROM   aqi_history
        WHERE  city_key = ?
          AND  DATE(fetch_time) >= ?
        ORDER  BY fetch_time DESC
        LIMIT  ?
    """, (city_key, date_from, limit)).fetchall()
    conn.close()

    data = [dict(r) for r in rows]

    return {
        "city_key":     city_key,
        "display_name": city["display_name"],
        "days":         days,
        "count":        len(data),
        "data":         data,
        "timestamp":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ===== GET /api/summary =====
@router.get("/summary", summary="取得所有城市今日摘要")
def get_summary():
    """
    取得今日各城市 AQI 統計摘要（平均、最高、最低）。
    適合官網首頁顯示。
    """
    from core.api_client import aqi_level

    today = datetime.now().strftime("%Y-%m-%d")

    conn = get_conn()
    rows = conn.execute("""
        SELECT w.city_key, w.display_name,
               AVG(h.aqi) as avg_aqi,
               MAX(h.aqi) as max_aqi,
               MIN(h.aqi) as min_aqi,
               COUNT(*)   as count
        FROM watch_list w
        LEFT JOIN aqi_history h ON w.city_key = h.city_key
            AND DATE(h.fetch_time) = ?
        WHERE w.is_active = 1
        GROUP BY w.city_key
        ORDER BY avg_aqi DESC
    """, (today,)).fetchall()
    conn.close()

    data = []
    for r in rows:
        lv, color, emoji = aqi_level(r["avg_aqi"])
        data.append({
            "city_key":     r["city_key"],
            "display_name": r["display_name"],
            "avg_aqi":      round(r["avg_aqi"], 1) if r["avg_aqi"] else None,
            "max_aqi":      r["max_aqi"],
            "min_aqi":      r["min_aqi"],
            "count":        r["count"],
            "aqi_level":    lv,
            "aqi_color":    color,
            "aqi_emoji":    emoji,
        })

    return {
        "date":      today,
        "count":     len(data),
        "data":      data,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
