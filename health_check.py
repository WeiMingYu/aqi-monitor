"""
health_check.py - AQI Monitor 健康檢查腳本
檢查項目：
  1. Python 環境與套件
  2. 資料庫連線與資料表完整性
  3. Streamlit 服務（port 8501）
  4. FastAPI 服務（port 8506）
  5. WAQI API 連線
  6. 資料新鮮度（最後抓取時間）
  7. 排程狀態
  8. 磁碟空間
  9. 訂閱會員發送狀態

執行方式：python health_check.py
"""

import sys
import os
import sqlite3
import requests
from datetime import datetime, timedelta

# ===== 設定 =====
PROJECT_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_PATH      = os.path.join(PROJECT_DIR, "data", "aqi_monitor.db")
STREAMLIT_URL = "http://localhost:8501"
FASTAPI_URL   = "http://localhost:8506"

# 顏色輸出（Windows CMD 支援）
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

PASS = f"{GREEN}✅ 正常{RESET}"
WARN = f"{YELLOW}⚠️  警告{RESET}"
FAIL = f"{RED}❌ 異常{RESET}"


def print_header():
    print(f"\n{BOLD}{'='*55}")
    print(f"  AQI Monitor 健康檢查")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*55}{RESET}\n")


def check_result(label: str, status: str, detail: str = ""):
    """統一輸出格式"""
    detail_str = f"  → {detail}" if detail else ""
    print(f"  {label:<30} {status}{detail_str}")


# ===== 1. Python 環境 =====
def check_python():
    print(f"{BOLD}[1] Python 環境{RESET}")
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10):
        check_result("Python 版本", PASS, version)
    else:
        check_result("Python 版本", WARN, f"{version}（建議 3.10 以上）")

    # 檢查關鍵套件
    packages = [
        ("streamlit",     "streamlit"),
        ("fastapi",       "fastapi"),
        ("uvicorn",       "uvicorn"),
        ("apscheduler",   "apscheduler"),
        ("pandas",        "pandas"),
        ("plotly",        "plotly"),
        ("openpyxl",      "openpyxl"),
        ("reportlab",     "reportlab"),
        ("python-pptx",   "pptx"),
        ("python-dotenv", "dotenv"),
        ("requests",      "requests"),
    ]
    for pkg_name, import_name in packages:
        try:
            __import__(import_name)
            check_result(f"套件 {pkg_name}", PASS)
        except ImportError:
            check_result(f"套件 {pkg_name}", FAIL, "未安裝")
    print()


# ===== 2. 資料庫 =====
def check_database():
    print(f"{BOLD}[2] 資料庫{RESET}")

    if not os.path.exists(DB_PATH):
        check_result("資料庫檔案", FAIL, f"找不到 {DB_PATH}")
        print()
        return

    db_size = os.path.getsize(DB_PATH) / 1024 / 1024
    check_result("資料庫檔案", PASS, f"{db_size:.2f} MB")

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        # 檢查資料表
        expected_tables = [
            "continent", "country", "station",
            "aqi_history", "aqi_forecast",
            "watch_list", "api_log",
            "settings", "alert_log",
            "subscribers", "subscription_log",
        ]
        existing = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]

        all_ok = True
        for t in expected_tables:
            if t not in existing:
                check_result(f"資料表 {t}", FAIL, "不存在")
                all_ok = False

        if all_ok:
            check_result("資料表完整性（11張）", PASS)

        # 各表記錄數
        key_tables = {
            "watch_list":  "監控城市",
            "aqi_history": "歷史資料",
            "subscribers": "訂閱會員",
            "alert_log":   "觸發記錄",
        }
        for t, label in key_tables.items():
            try:
                cnt = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                check_result(f"{label}（{t}）", PASS, f"{cnt} 筆")
            except Exception:
                check_result(f"{label}（{t}）", FAIL, "查詢失敗")

        conn.close()

    except Exception as e:
        check_result("資料庫連線", FAIL, str(e))
    print()


# ===== 3. Streamlit 服務 =====
def check_streamlit():
    print(f"{BOLD}[3] Streamlit 服務（port 8501）{RESET}")
    try:
        resp = requests.get(STREAMLIT_URL, timeout=5)
        if resp.status_code == 200:
            check_result("Streamlit 服務", PASS, f"HTTP {resp.status_code}")
        else:
            check_result("Streamlit 服務", WARN, f"HTTP {resp.status_code}")
    except requests.exceptions.ConnectionError:
        check_result("Streamlit 服務", FAIL, "無法連線，服務可能未啟動")
    except requests.exceptions.Timeout:
        check_result("Streamlit 服務", WARN, "連線逾時")
    except Exception as e:
        check_result("Streamlit 服務", FAIL, str(e))
    print()


# ===== 4. FastAPI 服務 =====
def check_fastapi():
    print(f"{BOLD}[4] FastAPI REST API（port 8506）{RESET}")
    try:
        resp = requests.get(f"{FASTAPI_URL}/", timeout=5)
        data = resp.json()
        if data.get("status") == "ok":
            check_result("FastAPI 服務", PASS, f"HTTP {resp.status_code}")
        else:
            check_result("FastAPI 服務", WARN, f"回應異常：{data}")
    except requests.exceptions.ConnectionError:
        check_result("FastAPI 服務", FAIL, "無法連線，服務可能未啟動")
    except Exception as e:
        check_result("FastAPI 服務", FAIL, str(e))

    # 測試 API 端點
    endpoints = [
        ("/api/cities",        "GET /api/cities"),
        ("/api/aqi/all",       "GET /api/aqi/all"),
        ("/api/alerts/recent", "GET /api/alerts/recent"),
    ]
    for path, label in endpoints:
        try:
            resp = requests.get(f"{FASTAPI_URL}{path}", timeout=5)
            if resp.status_code == 200:
                check_result(label, PASS)
            else:
                check_result(label, WARN, f"HTTP {resp.status_code}")
        except Exception as e:
            check_result(label, FAIL, str(e))
    print()


# ===== 5. WAQI API 連線 =====
def check_waqi():
    print(f"{BOLD}[5] WAQI API 連線{RESET}")
    try:
        # 從 DB 讀取 token
        conn   = sqlite3.connect(DB_PATH)
        row    = conn.execute(
            "SELECT value FROM settings WHERE key = 'waqi_token'"
        ).fetchone()
        conn.close()
        token  = row[0] if row else "demo"

        url    = f"https://api.waqi.info/feed/@1597/?token={token}"
        resp   = requests.get(url, timeout=8)
        data   = resp.json()

        if data.get("status") == "ok":
            aqi = data["data"].get("aqi", "N/A")
            check_result("WAQI API", PASS, f"台北中山站 AQI={aqi}")
            if token == "demo":
                check_result("API Token", WARN, "使用 demo token，建議申請正式 token")
            else:
                check_result("API Token", PASS, f"{token[:6]}****")
        else:
            check_result("WAQI API", FAIL, data.get("data", "回應異常"))

    except requests.exceptions.Timeout:
        check_result("WAQI API", WARN, "連線逾時，請檢查網路")
    except Exception as e:
        check_result("WAQI API", FAIL, str(e))
    print()


# ===== 6. 資料新鮮度 =====
def check_data_freshness():
    print(f"{BOLD}[6] 資料新鮮度{RESET}")
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        # 最後抓取時間
        row = conn.execute("""
            SELECT city_key, fetch_time
            FROM   aqi_history
            ORDER  BY fetch_time DESC
            LIMIT  1
        """).fetchone()

        if row:
            last_fetch = datetime.strptime(row["fetch_time"], "%Y-%m-%d %H:%M:%S")
            age_minutes = (datetime.now() - last_fetch).total_seconds() / 60

            if age_minutes <= 60:
                check_result("最後抓取時間", PASS,
                             f"{row['fetch_time']}（{age_minutes:.0f} 分鐘前）")
            elif age_minutes <= 120:
                check_result("最後抓取時間", WARN,
                             f"{row['fetch_time']}（{age_minutes:.0f} 分鐘前，排程可能異常）")
            else:
                check_result("最後抓取時間", FAIL,
                             f"{row['fetch_time']}（{age_minutes/60:.1f} 小時前，排程異常！）")
        else:
            check_result("最後抓取時間", WARN, "尚無資料，請啟動排程並等待抓取")

        # 今日資料筆數
        today = datetime.now().strftime("%Y-%m-%d")
        cnt   = conn.execute(
            "SELECT COUNT(*) FROM aqi_history WHERE DATE(fetch_time) = ?", (today,)
        ).fetchone()[0]
        check_result(f"今日資料筆數（{today}）", PASS if cnt > 0 else WARN, f"{cnt} 筆")

        # 各城市最後更新
        cities = conn.execute("""
            SELECT w.display_name, MAX(h.fetch_time) as last_time
            FROM   watch_list w
            LEFT JOIN aqi_history h ON w.city_key = h.city_key
            WHERE  w.is_active = 1
            GROUP  BY w.city_key
            ORDER  BY w.id
        """).fetchall()

        for city in cities:
            if city["last_time"]:
                last = datetime.strptime(city["last_time"], "%Y-%m-%d %H:%M:%S")
                age  = (datetime.now() - last).total_seconds() / 60
                status = PASS if age <= 90 else WARN
                check_result(f"  {city['display_name']}", status,
                             f"{city['last_time']}（{age:.0f}分鐘前）")
            else:
                check_result(f"  {city['display_name']}", WARN, "尚無資料")

        conn.close()

    except Exception as e:
        check_result("資料新鮮度檢查", FAIL, str(e))
    print()


# ===== 7. Email / LINE 設定 =====
def check_notification_settings():
    print(f"{BOLD}[7] 通知設定{RESET}")
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        keys = ["webhook_url", "line_channel_token", "line_target_id",
                "email_account", "email_recipients"]
        settings = {}
        for k in keys:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (k,)).fetchone()
            settings[k] = row["value"] if row else ""
        conn.close()

        check_result("Webhook URL",
                     PASS if settings["webhook_url"] else WARN,
                     settings["webhook_url"][:30] + "..." if settings["webhook_url"] else "未設定")
        check_result("LINE Token",
                     PASS if settings["line_channel_token"] else WARN,
                     "已設定" if settings["line_channel_token"] else "未設定")
        check_result("LINE 目標 ID",
                     PASS if settings["line_target_id"] else WARN,
                     settings["line_target_id"] if settings["line_target_id"] else "未設定")
        check_result("Email 帳號",
                     PASS if settings["email_account"] else WARN,
                     settings["email_account"] if settings["email_account"] else "未設定")
        check_result("Email 收件人",
                     PASS if settings["email_recipients"] else WARN,
                     settings["email_recipients"][:40] if settings["email_recipients"] else "未設定")

    except Exception as e:
        check_result("通知設定檢查", FAIL, str(e))
    print()


# ===== 8. 磁碟空間 =====
def check_disk():
    print(f"{BOLD}[8] 磁碟空間{RESET}")
    try:
        import shutil
        total, used, free = shutil.disk_usage(PROJECT_DIR)
        free_gb  = free  / 1024**3
        total_gb = total / 1024**3
        used_pct = used / total * 100

        if free_gb >= 5:
            status = PASS
        elif free_gb >= 2:
            status = WARN
        else:
            status = FAIL

        check_result("磁碟剩餘空間", status,
                     f"{free_gb:.1f} GB 可用 / {total_gb:.1f} GB 總計（已用 {used_pct:.1f}%）")

        # DB 檔案大小
        if os.path.exists(DB_PATH):
            db_mb = os.path.getsize(DB_PATH) / 1024**2
            check_result("資料庫大小", PASS, f"{db_mb:.2f} MB")

        # Log 資料夾大小
        log_dir = os.path.join(PROJECT_DIR, "logs")
        if os.path.exists(log_dir):
            log_size = sum(
                os.path.getsize(os.path.join(log_dir, f))
                for f in os.listdir(log_dir)
                if os.path.isfile(os.path.join(log_dir, f))
            ) / 1024**2
            check_result("Log 資料夾大小", PASS if log_size < 100 else WARN,
                         f"{log_size:.2f} MB")

    except Exception as e:
        check_result("磁碟空間檢查", FAIL, str(e))
    print()


# ===== 9. 訂閱會員 =====
def check_subscribers():
    print(f"{BOLD}[9] 訂閱會員發送狀態{RESET}")
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        total   = conn.execute("SELECT COUNT(*) FROM subscribers WHERE is_active=1").fetchone()[0]
        check_result("啟用中會員", PASS if total > 0 else WARN, f"{total} 位")

        # 最近發送記錄
        last = conn.execute("""
            SELECT sent_at, status, COUNT(*) as cnt
            FROM   subscription_log
            GROUP  BY DATE(sent_at)
            ORDER  BY sent_at DESC
            LIMIT  1
        """).fetchone()

        if last:
            check_result("最近發送記錄", PASS, f"{last['sent_at'][:10]} 共 {last['cnt']} 筆")
        else:
            check_result("最近發送記錄", WARN, "尚無發送記錄")

        # 失敗記錄
        fail_cnt = conn.execute(
            "SELECT COUNT(*) FROM subscription_log WHERE status='failed'"
        ).fetchone()[0]
        check_result("發送失敗記錄", PASS if fail_cnt == 0 else WARN, f"{fail_cnt} 筆")

        conn.close()

    except Exception as e:
        check_result("訂閱會員檢查", FAIL, str(e))
    print()


# ===== 主程式 =====
def main():
    # 啟用 Windows 顏色支援
    os.system("color")

    print_header()
    check_python()
    check_database()
    check_streamlit()
    check_fastapi()
    check_waqi()
    check_data_freshness()
    check_notification_settings()
    check_disk()
    check_subscribers()

    print(f"{BOLD}{'='*55}")
    print(f"  健康檢查完成：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*55}{RESET}\n")


if __name__ == "__main__":
    main()
