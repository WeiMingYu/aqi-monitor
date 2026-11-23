"""
core/scheduler.py - 背景排程模組（APScheduler 版）
使用 APScheduler BackgroundScheduler，Streamlit 重啟後可自動恢復
觸發邏輯：AQI 超閾值 + 冷卻控制 + Webhook + LINE + Email 通知
"""

import sqlite3
import requests
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval     import IntervalTrigger

from core.db_init    import get_conn
from core.api_client import fetch_by_city


# ===== 1. 全域排程器實例（模組層級單例）=====
_scheduler = BackgroundScheduler(timezone="Asia/Taipei")
_job_id    = "aqi_fetch_job"   # 固定 job ID，方便管理


# ===== 2. 讀取系統設定 =====

def _get_setting(key: str, default: str = "") -> str:
    """從 settings 表讀取單一設定值"""
    try:
        conn = get_conn()
        row  = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        conn.close()
        return row["value"] if row else default
    except Exception:
        return default


# ===== 3. Webhook 發送 =====

def _send_webhook(payload: dict) -> tuple:
    """發送 AQI 觸發事件到 Webhook URL，URL 未設定回傳 skipped"""
    webhook_url    = _get_setting("webhook_url",    "")
    webhook_secret = _get_setting("webhook_secret", "")

    if not webhook_url.strip():
        return False, "skipped"

    try:
        headers = {"Content-Type": "application/json"}
        if webhook_secret:
            headers["X-Webhook-Secret"] = webhook_secret
        resp = requests.post(webhook_url, json=payload, headers=headers, timeout=10)
        if resp.status_code in (200, 201, 204):
            return True, f"HTTP {resp.status_code}"
        else:
            return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    except requests.exceptions.Timeout:
        return False, "連線逾時"
    except requests.exceptions.RequestException as e:
        return False, str(e)


# ===== 4. 觸發判斷與通知 =====

def _check_and_trigger(city_key: str, display_name: str,
                        aqi, threshold: int, now_str: str) -> bool:
    """
    判斷是否需要觸發警報，執行 Webhook + LINE + Email + alert_log。
    """
    # ---- 4-1. AQI 未超閾值 ----
    if aqi is None:
        return False
    try:
        aqi_val = float(aqi)
    except (ValueError, TypeError):
        return False

    if aqi_val <= threshold:
        return False

    # ---- 4-2. 冷卻時間檢查 ----
    try:
        cooldown_hours = int(_get_setting("alert_cooldown_hours", "24"))
    except ValueError:
        cooldown_hours = 24

    try:
        conn     = get_conn()
        last_row = conn.execute("""
            SELECT triggered_at FROM alert_log
            WHERE  city_key = ?
            ORDER  BY triggered_at DESC
            LIMIT  1
        """, (city_key,)).fetchone()
        conn.close()
    except Exception:
        last_row = None

    if last_row and last_row["triggered_at"]:
        try:
            last_time = datetime.strptime(last_row["triggered_at"], "%Y-%m-%d %H:%M:%S")
            elapsed   = (datetime.now() - last_time).total_seconds() / 3600
            if elapsed < cooldown_hours:
                print(f"  ⏳ {display_name} AQI={aqi_val} 超閾值，冷卻中"
                      f"（{elapsed:.1f}h / {cooldown_hours}h）")
                return False
        except ValueError:
            pass

    # ---- 4-3. Webhook ----
    webhook_url = _get_setting("webhook_url", "")
    payload = {
        "event":        "aqi_alert",
        "city_key":     city_key,
        "display_name": display_name,
        "aqi":          aqi_val,
        "threshold":    threshold,
        "triggered_at": now_str,
    }
    ok, response_msg = _send_webhook(payload)
    webhook_status   = "skipped" if response_msg == "skipped" else ("sent" if ok else "failed")

    # ---- 4-4. 寫入 alert_log ----
    try:
        conn = get_conn()
        conn.execute("""
            INSERT INTO alert_log
                (city_key, display_name, aqi, threshold,
                 webhook_url, webhook_status, webhook_response, triggered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (city_key, display_name, aqi_val, threshold,
               webhook_url, webhook_status, response_msg, now_str))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"  ❌ alert_log 寫入失敗：{e}")

    # ---- 4-5. LINE 通知 ----
    try:
        from core.notify_line import send_aqi_alert as line_alert
        line_ok, line_msg = line_alert(display_name, city_key, aqi_val, threshold)
        if line_ok:
            print(f"  💬 LINE 通知已發送：{display_name}")
        elif line_msg != "line_not_configured":
            print(f"  ⚠️ LINE 通知失敗：{line_msg}")
    except Exception as e:
        print(f"  ❌ LINE 通知例外：{e}")

    # ---- 4-6. Email 通知 ----
    try:
        from core.notify_email import send_aqi_alert as email_alert
        email_ok, email_msg = email_alert(display_name, city_key, aqi_val, threshold)
        if email_ok:
            print(f"  📧 Email 通知已發送：{display_name}")
        elif email_msg != "email_not_configured":
            print(f"  ⚠️ Email 通知失敗：{email_msg}")
    except Exception as e:
        print(f"  ❌ Email 通知例外：{e}")

    # ---- 4-7. Console 輸出 ----
    status_emoji = {"sent": "📤", "skipped": "📝", "failed": "❌"}.get(webhook_status, "❓")
    print(f"  🚨 {display_name} AQI={aqi_val} 超閾值 {threshold}  "
          f"{status_emoji} Webhook={webhook_status}")

    return True


# ===== 5. 核心抓取函數 =====

def fetch_and_save(city_key: str) -> dict:
    """
    抓取單一城市 AQI 並存入 DB，之後執行觸發判斷。
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    result = fetch_by_city(city_key)
    conn   = get_conn()
    c      = conn.cursor()

    # ---- API log ----
    c.execute(
        "INSERT INTO api_log (city_key, status, message, call_time) VALUES (?, ?, ?, ?)",
        (city_key,
         "ok" if result["ok"] else "error",
         "" if result["ok"] else result.get("error", ""),
         now_str)
    )

    saved     = False
    triggered = False

    if result["ok"]:
        d = result["data"]
        try:
            c.execute("""
                INSERT OR IGNORE INTO aqi_history (
                    city_key, station_name,
                    aqi, pm25, pm10, no2, co, so2, o3,
                    temp, humidity, wind, pressure,
                    measure_time, fetch_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                city_key, d.get("station_name"),
                d.get("aqi"), d.get("pm25"), d.get("pm10"),
                d.get("no2"), d.get("co"),   d.get("so2"), d.get("o3"),
                d.get("temp"), d.get("humidity"), d.get("wind"), d.get("pressure"),
                d.get("measure_time"), now_str,
            ))

            for pollutant, records in d.get("forecast", {}).items():
                for r in records:
                    if r.get("day"):
                        c.execute("""
                            INSERT OR IGNORE INTO aqi_forecast
                                (city_key, pollutant, forecast_day,
                                 avg_val, max_val, min_val, fetch_time)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (city_key, pollutant, r["day"],
                               r.get("avg"), r.get("max"), r.get("min"), now_str))

            conn.commit()
            saved = True

        except sqlite3.Error as e:
            conn.rollback()
            result = {"ok": False, "error": f"DB 錯誤：{e}"}

    conn.close()

    # ---- 觸發判斷 ----
    if saved:
        try:
            conn2  = get_conn()
            wl_row = conn2.execute(
                "SELECT display_name, alert_threshold FROM watch_list WHERE city_key = ?",
                (city_key,)
            ).fetchone()
            conn2.close()

            if wl_row:
                triggered = _check_and_trigger(
                    city_key     = city_key,
                    display_name = wl_row["display_name"] or city_key,
                    aqi          = result["data"].get("aqi"),
                    threshold    = wl_row["alert_threshold"] or 100,
                    now_str      = now_str,
                )
        except Exception as e:
            print(f"  ❌ 觸發判斷失敗：{e}")

    return {**result, "saved": saved, "triggered": triggered, "city_key": city_key}


# ===== 6. 批次抓取所有監控清單城市（APScheduler 呼叫此函式）=====

def _run_subscription_send():
    """訂閱發送包裝函式，供 APScheduler 呼叫"""
    try:
        from core.notify_daily import send_scheduled_reports
        send_scheduled_reports()
    except Exception as e:
        print(f"❌ 訂閱發送失敗：{e}")

def fetch_all_watchlist():
    """抓取所有 watch_list 城市，APScheduler job 的實際執行函式"""
    import time
    print(f"\n⏰ [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 排程執行：批次抓取...")

    conn   = get_conn()
    cities = conn.execute(
        "SELECT city_key, display_name FROM watch_list WHERE is_active = 1 ORDER BY id"
    ).fetchall()
    conn.close()

    if not cities:
        print("  ⚠️ 監控清單是空的，跳過")
        return

    results    = []
    for row in cities:
        print(f"  📡 {row['display_name']} ({row['city_key']})")
        results.append(fetch_and_save(row["city_key"]))
        time.sleep(0.5)

    ok_count   = sum(1 for r in results if r["ok"])
    trig_count = sum(1 for r in results if r.get("triggered"))
    print(f"  ✅ 完成：{ok_count}/{len(results)} 個城市成功"
          f"{'，' + str(trig_count) + ' 個觸發警報' if trig_count else ''}")


# ===== 7. APScheduler 控制函式 =====

def start_scheduler(interval_seconds: int = 3600) -> bool:
    from core.db_init import DEMO_MODE
    if DEMO_MODE:
        return False   # 展示版不啟動排程，避免對外呼叫與寫入
    """
    啟動排程。
    若排程器未啟動先啟動，再新增/更新 job。
    已有相同 job 時更新間隔（reschedule）。

    Args:
        interval_seconds: 抓取間隔（秒）
    Returns:
        bool：True=成功啟動或更新
    """
    global _scheduler

    try:
        # ---- 啟動排程器（若未啟動）----
        if not _scheduler.running:
            _scheduler.start()
            print(f"🕐 APScheduler 已啟動")

        # ---- 新增或更新 AQI 抓取 job ----
        trigger = IntervalTrigger(seconds=interval_seconds, timezone="Asia/Taipei")

        if _scheduler.get_job(_job_id):
            _scheduler.reschedule_job(_job_id, trigger=trigger)
            print(f"🔄 排程已更新：每 {interval_seconds//60} 分鐘")
        else:
            _scheduler.add_job(
                func             = fetch_all_watchlist,
                trigger          = trigger,
                id               = _job_id,
                name             = "AQI 批次抓取",
                replace_existing = True,
                misfire_grace_time = 60,
            )
            print(f"➕ 排程已新增：每 {interval_seconds//60} 分鐘")

        # ---- 新增每小時訂閱發送 job（若不存在）----
        _sub_job_id = "subscription_send_job"
        if not _scheduler.get_job(_sub_job_id):
            from apscheduler.triggers.cron import CronTrigger
            _scheduler.add_job(
                func             = _run_subscription_send,
                trigger          = CronTrigger(minute=0, timezone="Asia/Taipei"),  # 每小時整點
                id               = _sub_job_id,
                name             = "訂閱報告發送",
                replace_existing = True,
                misfire_grace_time = 300,
            )
            print("➕ 訂閱發送排程已新增（每小時整點檢查）")

        return True

    except Exception as e:
        print(f"❌ 排程啟動失敗：{e}")
        return False


def stop_scheduler():
    """移除 job（不停止 scheduler 本體，避免影響 APScheduler 內部狀態）"""
    global _scheduler
    try:
        if _scheduler.get_job(_job_id):
            _scheduler.remove_job(_job_id)
            print("🛑 排程 job 已移除")
    except Exception as e:
        print(f"❌ 移除排程失敗：{e}")


def is_running() -> bool:
    """檢查排程 job 是否存在且排程器正在運作"""
    return _scheduler.running and _scheduler.get_job(_job_id) is not None


def get_next_run_time() -> str:
    """取得下次執行時間字串"""
    try:
        job = _scheduler.get_job(_job_id)
        if job and job.next_run_time:
            return job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    return "N/A"
