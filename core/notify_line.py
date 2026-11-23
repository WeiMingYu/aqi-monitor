"""
core/notify_line.py - LINE Messaging API 通知模組
功能：AQI 超標時發送 LINE 推播通知
"""

import requests
from datetime import datetime


# ===== 1. 取得設定 =====

def _get_line_settings() -> tuple:
    """
    從 settings 表讀取 LINE 設定。
    Returns:
        (token, target_id)
    """
    try:
        from core.db_init import get_conn
        conn = get_conn()
        rows = conn.execute(
            "SELECT key, value FROM settings WHERE key IN ('line_channel_token', 'line_target_id')"
        ).fetchall()
        conn.close()
        settings = {r["key"]: r["value"] for r in rows}
        return (
            settings.get("line_channel_token", ""),
            settings.get("line_target_id", ""),
        )
    except Exception:
        return "", ""


# ===== 2. AQI 等級文字 =====

def _aqi_label(aqi_val) -> str:
    try:
        v = float(aqi_val)
    except (TypeError, ValueError):
        return "未知"
    if v <= 50:   return "🟢 優良"
    if v <= 100:  return "🟡 普通"
    if v <= 150:  return "🟠 敏感族群不健康"
    if v <= 200:  return "🔴 不健康"
    if v <= 300:  return "🟣 非常不健康"
    return             "⚫ 危險"


# ===== 3. 發送 LINE 通知 =====

def send_aqi_alert(city_name: str, city_key: str,
                   aqi: float, threshold: int) -> tuple:
    """
    發送 AQI 超標 LINE 推播通知。

    Args:
        city_name:  城市顯示名稱
        city_key:   WAQI 識別碼
        aqi:        當前 AQI 值
        threshold:  警戒閾值
    Returns:
        (bool, str)：(是否成功, 訊息)
    """
    token, target_id = _get_line_settings()

    # ---- 未設定就跳過 ----
    if not token or not target_id:
        return False, "line_not_configured"

    # ---- 組合訊息內容 ----
    now_str  = datetime.now().strftime("%Y-%m-%d %H:%M")
    lv_text  = _aqi_label(aqi)
    over     = int(aqi) - threshold

    message = (
        f"🚨 AQI 空氣品質警報\n"
        f"{'─' * 20}\n"
        f"📍 地點：{city_name}\n"
        f"📊 AQI：{int(aqi)}（超閾值 +{over}）\n"
        f"🎯 等級：{lv_text}\n"
        f"⚠️ 閾值：{threshold}\n"
        f"🕐 時間：{now_str}\n"
        f"{'─' * 20}\n"
        f"請注意防護，減少戶外活動。"
    )

    # ---- 發送 API 請求 ----
    try:
        url     = "https://api.line.me/v2/bot/message/push"
        headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {token}",
        }
        payload = {
            "to":       target_id,
            "messages": [{"type": "text", "text": message}],
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=10)

        if resp.status_code == 200:
            return True, "line_sent"
        else:
            return False, f"LINE API 錯誤（HTTP {resp.status_code}）：{resp.text[:100]}"

    except requests.exceptions.Timeout:
        return False, "LINE 連線逾時"
    except Exception as e:
        return False, f"LINE 發送失敗：{e}"


# ===== 4. 發送月報通知 =====

def send_report_ready(city_names: list, year: int, month: int) -> tuple:
    """
    月報產生後發送 LINE 通知。

    Args:
        city_names: 城市名稱清單
        year:       報告年份
        month:      報告月份
    Returns:
        (bool, str)
    """
    token, target_id = _get_line_settings()

    if not token or not target_id:
        return False, "line_not_configured"

    message = (
        f"📊 空氣品質月報已產生\n"
        f"{'─' * 20}\n"
        f"📅 期間：{year} 年 {month:02d} 月\n"
        f"📍 城市：{'、'.join(city_names)}\n"
        f"🕐 產生時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"{'─' * 20}\n"
        f"請至系統下載 Excel / PDF / PPT 報告。"
    )

    try:
        url     = "https://api.line.me/v2/bot/message/push"
        headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {token}",
        }
        payload = {
            "to":       target_id,
            "messages": [{"type": "text", "text": message}],
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=10)

        if resp.status_code == 200:
            return True, "line_sent"
        else:
            return False, f"LINE API 錯誤（HTTP {resp.status_code}）"

    except Exception as e:
        return False, f"LINE 發送失敗：{e}"
