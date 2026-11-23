"""
api/routes/alerts.py - 觸發事件記錄 API 路由
提供 AQI 超標觸發記錄查詢
"""

from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime, timedelta

from core.db_init import get_conn

router = APIRouter()


# ===== GET /api/alerts/recent =====
@router.get("/alerts/recent", summary="取得最近觸發記錄")
def get_recent_alerts(
    limit: int = Query(default=20, ge=1, le=100, description="最大回傳筆數"),
    city_key: Optional[str] = Query(default=None,  description="篩選特定城市"),
    status:   Optional[str] = Query(default=None,  description="篩選狀態：sent / skipped / failed"),
):
    """
    取得最近的 AQI 觸發事件記錄。

    參數：
    - **limit**：最大回傳筆數（預設 20，最多 100）
    - **city_key**：篩選特定城市（選填）
    - **status**：篩選 Webhook 狀態（選填）
    """
    where  = ["1=1"]
    params = []

    if city_key:
        where.append("city_key = ?")
        params.append(city_key)

    if status:
        where.append("webhook_status = ?")
        params.append(status)

    params.append(limit)

    conn = get_conn()
    rows = conn.execute(f"""
        SELECT id, city_key, display_name, aqi, threshold,
               webhook_status, triggered_at
        FROM   alert_log
        WHERE  {' AND '.join(where)}
        ORDER  BY triggered_at DESC
        LIMIT  ?
    """, params).fetchall()
    conn.close()

    data = [dict(r) for r in rows]

    return {
        "count":     len(data),
        "data":      data,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ===== GET /api/alerts/stats =====
@router.get("/alerts/stats", summary="觸發事件統計")
def get_alert_stats(
    days: int = Query(default=30, ge=1, le=365, description="統計天數"),
):
    """
    取得指定天數內的觸發事件統計。
    """
    date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    conn = get_conn()

    # 總計
    total = conn.execute(
        "SELECT COUNT(*) FROM alert_log WHERE DATE(triggered_at) >= ?", (date_from,)
    ).fetchone()[0]

    # 依狀態分組
    by_status = conn.execute("""
        SELECT webhook_status, COUNT(*) as cnt
        FROM   alert_log
        WHERE  DATE(triggered_at) >= ?
        GROUP  BY webhook_status
    """, (date_from,)).fetchall()

    # 依城市分組（觸發次數最多的前 10）
    by_city = conn.execute("""
        SELECT city_key, display_name, COUNT(*) as cnt,
               MAX(aqi) as max_aqi
        FROM   alert_log
        WHERE  DATE(triggered_at) >= ?
        GROUP  BY city_key
        ORDER  BY cnt DESC
        LIMIT  10
    """, (date_from,)).fetchall()

    conn.close()

    return {
        "days":      days,
        "total":     total,
        "by_status": {r["webhook_status"]: r["cnt"] for r in by_status},
        "by_city":   [dict(r) for r in by_city],
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
