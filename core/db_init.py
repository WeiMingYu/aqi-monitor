# ============================================================
# core/db_init.py
# 空氣品質監測系統 - 資料庫初始化模組
# 功能：建立所有資料表、索引（冪等設計，可重複執行）
# DB 路徑：data/aqi_monitor.db
# 作者：俞威名
# ============================================================
#
# ===== 資料表清單（共 9 張）=====
#   continent    洲別主檔
#   country      國家主檔
#   station      監測站主檔（WAQI uid 為 PK）
#   aqi_history  AQI 歷史快照（以 city_key 為主）
#   aqi_forecast AQI 預報資料（以 city_key 為主）
#   watch_list   使用者關注清單
#   api_log      API 呼叫日誌
#   settings     系統設定（key/value 格式）
#   alert_log    AQI 觸發事件 + Webhook 發送記錄
# ============================================================

import sqlite3
import os
import logging
from datetime import datetime

# ===== 1. 基本設定 =====

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# DB 路徑（相對於專案根目錄）
# DEMO 模式（AQI_DEMO_MODE=1）：使用 data/demo/ 內去識別化的展示資料庫，並停用排程與通知
DEMO_MODE = os.getenv("AQI_DEMO_MODE", "0") == "1"
_DATA_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_DIR  = os.path.join(_DATA_ROOT, "demo") if DEMO_MODE else _DATA_ROOT
DB_PATH = os.path.join(DB_DIR, "aqi_monitor.db")


# ===== 2. 取得資料庫連線 =====

def get_connection() -> sqlite3.Connection:
    """
    取得 SQLite 連線，並啟用外鍵約束（SQLite 預設關閉）。
    Returns:
        sqlite3.Connection：資料庫連線物件
    """
    os.makedirs(DB_DIR, exist_ok=True)          # 確保 data/ 資料夾存在
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")    # 啟用外鍵約束
    conn.row_factory = sqlite3.Row              # 讓查詢結果可用欄位名稱存取
    return conn

# 短名稱 alias，供其他模組 import 使用
get_conn = get_connection


# ===== 3. 建立資料表 SQL 定義 =====

# ---------- 3-1. continent 洲別主檔 ----------
SQL_CREATE_CONTINENT = """
CREATE TABLE IF NOT EXISTS continent (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,  -- 主鍵，自動遞增
    code         TEXT    NOT NULL UNIQUE,             -- 洲別代碼，如 AS / EU / AF
    name_en      TEXT    NOT NULL,                   -- 英文名稱
    name_zh      TEXT    NOT NULL,                   -- 中文名稱
    sort_order   INTEGER DEFAULT 0,                  -- 排序權重（數字小的排前面）
    is_active    INTEGER DEFAULT 1,                  -- 啟用狀態 1=啟用 0=停用
    spare1       TEXT,                               -- 預留文字欄1
    spare2       TEXT,                               -- 預留文字欄2
    spare_int1   INTEGER,                            -- 預留整數欄1
    spare_num1   REAL                                -- 預留數值欄1
);
"""

# ---------- 3-2. country 國家主檔 ----------
SQL_CREATE_COUNTRY = """
CREATE TABLE IF NOT EXISTS country (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,  -- 主鍵
    iso2             TEXT    NOT NULL UNIQUE,             -- ISO 3166-1 alpha-2，如 TW / US
    iso3             TEXT    UNIQUE,                     -- ISO 3166-1 alpha-3，如 TWN / USA
    name_en          TEXT    NOT NULL,                   -- 英文名稱
    name_zh          TEXT    NOT NULL,                   -- 中文名稱
    continent_id     INTEGER NOT NULL,                   -- FK → continent.id
    timezone_default TEXT,                               -- 預設時區，如 Asia/Taipei
    is_active        INTEGER DEFAULT 1,                  -- 啟用狀態
    sort_order       INTEGER DEFAULT 0,                  -- 排序權重
    spare1           TEXT,
    spare2           TEXT,
    spare_int1       INTEGER,
    spare_num1       REAL,
    FOREIGN KEY (continent_id) REFERENCES continent(id) ON UPDATE CASCADE
);
"""

# ---------- 3-3. station 監測站主檔 ----------
SQL_CREATE_STATION = """
CREATE TABLE IF NOT EXISTS station (
    uid          INTEGER PRIMARY KEY,   -- WAQI 官方 uid（直接用 WAQI uid，不自動遞增）
    name_en      TEXT,                  -- 英文站名
    name_zh      TEXT,                  -- 中文站名
    lat          REAL,                  -- 緯度（WGS84）
    lon          REAL,                  -- 經度（WGS84）
    country_id   INTEGER,               -- FK → country.id
    admin1       TEXT,                  -- 行政區第一層（省 / 州 / 縣市）
    admin2       TEXT,                  -- 行政區第二層（市 / 區 / 鄉鎮）
    timezone     TEXT,                  -- 本地時區，如 Asia/Taipei
    altitude     REAL,                  -- 海拔高度（公尺）
    station_type TEXT,                  -- 站點類型：official / unofficial / personal
    is_active    INTEGER DEFAULT 1,     -- 啟用狀態
    last_sync    TEXT,                  -- 最後同步時間（ISO8601）
    remark       TEXT,                  -- 備註
    spare1       TEXT,
    spare2       TEXT,
    spare_int1   INTEGER,
    spare_num1   REAL,
    FOREIGN KEY (country_id) REFERENCES country(id) ON UPDATE CASCADE
);
"""

# ---------- 3-4. aqi_history AQI 歷史快照 ----------
SQL_CREATE_AQI_HISTORY = """
CREATE TABLE IF NOT EXISTS aqi_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    city_key     TEXT    NOT NULL,                  -- WAQI 識別碼，如 @1597（對應 watch_list.city_key）
    station_name TEXT,                              -- 站台名稱（冗餘存，顯示用，避免 JOIN）
    aqi          REAL,                              -- 綜合 AQI 數值
    pm25         REAL,                              -- PM2.5 濃度（μg/m³）
    pm10         REAL,                              -- PM10  濃度（μg/m³）
    no2          REAL,                              -- 二氧化氮（ppb）
    co           REAL,                              -- 一氧化碳（ppm）
    so2          REAL,                              -- 二氧化硫（ppb）
    o3           REAL,                              -- 臭氧（ppb）
    temp         REAL,                              -- 溫度（°C）
    humidity     REAL,                              -- 相對濕度（%）
    wind         REAL,                              -- 風速（m/s）
    pressure     REAL,                              -- 氣壓（hPa）
    measure_time TEXT,                              -- 量測時間（ISO8601，站點當地時間）
    fetch_time   TEXT DEFAULT (datetime('now')),    -- 系統抓取時間
    data_source  TEXT DEFAULT 'waqi',               -- 資料來源
    spare1       TEXT,
    spare2       TEXT,
    spare_int1   INTEGER,
    spare_num1   REAL
);
"""

# ---------- 3-5. aqi_forecast AQI 預報資料 ----------
SQL_CREATE_AQI_FORECAST = """
CREATE TABLE IF NOT EXISTS aqi_forecast (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    city_key     TEXT    NOT NULL,                  -- WAQI 識別碼（主要查詢鍵）
    station_uid  INTEGER,                           -- FK → station.uid（允許 NULL，station 表尚未對應時）
    pollutant    TEXT    NOT NULL,                  -- 污染物：pm25 / pmp10 / o3 / uvi
                                                    -- ⚠️ 注意：PM10 的 key 是 pmp10（WAQI API 設計不一致）
    forecast_day TEXT    NOT NULL,                  -- 預報日期（YYYY-MM-DD）
    avg_val      REAL,                              -- 當日預報平均值
    max_val      REAL,                              -- 當日預報最大值
    min_val      REAL,                              -- 當日預報最小值
    fetch_time   TEXT DEFAULT (datetime('now')),    -- 資料抓取時間
    spare1       TEXT,
    spare2       TEXT,
    spare_int1   INTEGER,
    spare_num1   REAL,
    FOREIGN KEY (station_uid) REFERENCES station(uid) ON UPDATE CASCADE
);
"""

# ---------- 3-6. watch_list 使用者關注清單 ----------
SQL_CREATE_WATCH_LIST = """
CREATE TABLE IF NOT EXISTS watch_list (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    city_key        TEXT    NOT NULL UNIQUE,            -- WAQI 識別碼（不做 FK，獨立存字串）
    display_name    TEXT,                               -- 自訂顯示名稱（覆蓋站台名稱）
    geo_lat         REAL,                               -- 緯度（加入時從 API 取得）
    geo_lon         REAL,                               -- 經度
    group_name      TEXT,                               -- 分組名稱，如「台灣」「辦公室」
    alert_threshold INTEGER DEFAULT 100,                -- AQI 警戒閾值，超過觸發通知
    is_active       INTEGER DEFAULT 1,                  -- 啟用狀態
    created_at      TEXT    DEFAULT (datetime('now')),  -- 建立時間
    note            TEXT,                               -- 備註
    spare1          TEXT,
    spare2          TEXT,
    spare_int1      INTEGER,
    spare_num1      REAL
);
"""

# ---------- 3-7. api_log API 呼叫日誌 ----------
SQL_CREATE_API_LOG = """
CREATE TABLE IF NOT EXISTS api_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    city_key    TEXT,                               -- WAQI 識別碼（允許 NULL：非城市級呼叫）
    station_uid INTEGER,                            -- FK → station.uid（允許 NULL）
    status      TEXT,                               -- ok / error / timeout / rate_limit
    message     TEXT,                               -- 回傳訊息或錯誤說明
    call_time   TEXT DEFAULT (datetime('now')),     -- 呼叫時間
    spare1      TEXT,
    spare2      TEXT,
    spare_int1  INTEGER,
    spare_num1  REAL,
    FOREIGN KEY (station_uid) REFERENCES station(uid) ON UPDATE CASCADE ON DELETE SET NULL
);
"""

# ---------- 3-8. settings 系統設定 ----------
SQL_CREATE_SETTINGS = """
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,                    -- 設定鍵名（唯一）
    value      TEXT,                                -- 設定值（統一存字串）
    updated_at TEXT DEFAULT (datetime('now'))       -- 最後更新時間
);
"""
# settings 預設 key 清單（由 tab_settings.py 負責初始化）：
#   waqi_token           WAQI API Token
#   webhook_url          Webhook 接收端點 URL
#   webhook_secret       Webhook 驗證密鑰
#   alert_cooldown_hours 同城市觸發冷卻時間（小時），預設 24
#   scheduler_interval   排程間隔（分鐘），預設 60

# ---------- 3-9. alert_log AQI 觸發事件記錄 ----------
SQL_CREATE_ALERT_LOG = """
CREATE TABLE IF NOT EXISTS alert_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    city_key         TEXT    NOT NULL,                 -- 觸發的城市識別碼
    display_name     TEXT,                             -- 城市顯示名稱（冗餘存，避免 JOIN）
    aqi              REAL,                             -- 觸發時的 AQI 值
    threshold        INTEGER,                          -- 觸發時使用的閾值
    webhook_url      TEXT,                             -- 發送目標 URL（記錄當時設定）
    webhook_status   TEXT,                             -- sent / skipped / failed
                                                       -- sent    = 成功發送
                                                       -- skipped = URL 未設定，只記錄不發送
                                                       -- failed  = 發送失敗
    webhook_response TEXT,                             -- Webhook 回應內容或錯誤訊息
    triggered_at     TEXT DEFAULT (datetime('now')),   -- 觸發時間
    spare1           TEXT,
    spare2           TEXT,
    spare_int1       INTEGER,
    spare_num1       REAL
);
"""

# ---------- 3-10. subscribers 訂閱會員主檔 ----------
SQL_CREATE_SUBSCRIBERS = """
CREATE TABLE IF NOT EXISTS subscribers (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,  -- 主鍵
    name         TEXT    NOT NULL,                   -- 會員姓名
    email        TEXT    NOT NULL UNIQUE,            -- Email（唯一）
    phone        TEXT,                               -- 電話（選填）
    plan         TEXT    NOT NULL DEFAULT 'monthly', -- 訂閱方案：daily / weekly / monthly
    cities       TEXT    NOT NULL DEFAULT '[]',      -- 訂閱城市 JSON，如 ["@1591","@1590"]
    send_hour    INTEGER NOT NULL DEFAULT 8,         -- 發送小時（0-23），預設早上8點
    send_weekday INTEGER DEFAULT 1,                  -- 週報：星期幾（0=週一 6=週日，weekly 才用）
    send_day     INTEGER DEFAULT 1,                  -- 月報：幾號（1-28，monthly 才用）
    is_active    INTEGER NOT NULL DEFAULT 1,         -- 1=啟用 0=停用
    created_at   TEXT    DEFAULT (datetime('now')),  -- 建立時間
    note         TEXT,                               -- 備註
    spare1       TEXT,                               -- 預留文字欄1
    spare2       TEXT,                               -- 預留文字欄2
    spare_int1   INTEGER,                            -- 預留整數欄1
    spare_num1   REAL                                -- 預留數值欄1
);
"""

# ---------- 3-11. subscription_log 訂閱發送記錄 ----------
SQL_CREATE_SUBSCRIPTION_LOG = """
CREATE TABLE IF NOT EXISTS subscription_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,  -- 主鍵
    subscriber_id INTEGER NOT NULL,                   -- FK → subscribers.id
    plan          TEXT,                               -- 發送的方案：daily / weekly / monthly
    report_type   TEXT,                               -- 報告格式：excel / pdf / ppt
    sent_at       TEXT    DEFAULT (datetime('now')),  -- 發送時間
    status        TEXT,                               -- sent / failed
    message       TEXT,                               -- 發送結果或錯誤訊息
    spare1        TEXT,                               -- 預留文字欄1
    spare_int1    INTEGER,                            -- 預留整數欄1
    FOREIGN KEY (subscriber_id) REFERENCES subscribers(id) ON DELETE CASCADE
);
"""


# ===== 4. 建立索引 SQL 定義 =====

SQL_INDEXES = [
    # -- country
    "CREATE INDEX IF NOT EXISTS idx_country_continent    ON country(continent_id);",
    "CREATE INDEX IF NOT EXISTS idx_country_iso2         ON country(iso2);",

    # -- station
    "CREATE INDEX IF NOT EXISTS idx_station_country      ON station(country_id);",
    "CREATE INDEX IF NOT EXISTS idx_station_active       ON station(is_active);",
    "CREATE INDEX IF NOT EXISTS idx_station_latlon       ON station(lat, lon);",

    # -- aqi_history（查詢最頻繁，索引要齊）
    "CREATE INDEX IF NOT EXISTS idx_aqihist_city         ON aqi_history(city_key);",
    "CREATE INDEX IF NOT EXISTS idx_aqihist_measure      ON aqi_history(measure_time);",
    "CREATE INDEX IF NOT EXISTS idx_aqihist_city_mt      ON aqi_history(city_key, measure_time);", # -- 複合索引：單站時序查詢

    # -- aqi_forecast
    "CREATE INDEX IF NOT EXISTS idx_aqifore_city         ON aqi_forecast(city_key);",
    "CREATE INDEX IF NOT EXISTS idx_aqifore_day          ON aqi_forecast(forecast_day);",
    "CREATE INDEX IF NOT EXISTS idx_aqifore_city_day     ON aqi_forecast(city_key, forecast_day);",

    # -- watch_list
    "CREATE INDEX IF NOT EXISTS idx_watchlist_city_key   ON watch_list(city_key);",
    "CREATE INDEX IF NOT EXISTS idx_watchlist_group      ON watch_list(group_name);",
    "CREATE INDEX IF NOT EXISTS idx_watchlist_active     ON watch_list(is_active);",

    # -- api_log
    "CREATE INDEX IF NOT EXISTS idx_apilog_city_key      ON api_log(city_key);",
    "CREATE INDEX IF NOT EXISTS idx_apilog_station       ON api_log(station_uid);",
    "CREATE INDEX IF NOT EXISTS idx_apilog_calltime      ON api_log(call_time);",
    "CREATE INDEX IF NOT EXISTS idx_apilog_status        ON api_log(status);",

    # -- alert_log
    "CREATE INDEX IF NOT EXISTS idx_alertlog_city        ON alert_log(city_key);",
    "CREATE INDEX IF NOT EXISTS idx_alertlog_triggered   ON alert_log(triggered_at);",
    "CREATE INDEX IF NOT EXISTS idx_alertlog_status      ON alert_log(webhook_status);",

    # -- subscribers
    "CREATE INDEX IF NOT EXISTS idx_subscribers_email    ON subscribers(email);",
    "CREATE INDEX IF NOT EXISTS idx_subscribers_plan     ON subscribers(plan);",
    "CREATE INDEX IF NOT EXISTS idx_subscribers_active   ON subscribers(is_active);",

    # -- subscription_log
    "CREATE INDEX IF NOT EXISTS idx_sublog_subscriber    ON subscription_log(subscriber_id);",
    "CREATE INDEX IF NOT EXISTS idx_sublog_sent_at       ON subscription_log(sent_at);",
    "CREATE INDEX IF NOT EXISTS idx_sublog_status        ON subscription_log(status);",
]


# ===== 5. 主初始化函式 =====

def init_db() -> bool:
    """
    初始化資料庫：建立所有資料表和索引。
    冪等設計：可重複執行，不會破壞現有資料。
    Returns:
        bool：True=成功，False=失敗
    """
    logger.info(f"[db_init] 開始初始化資料庫：{DB_PATH}")

    # 依外鍵依賴順序排列（被參考的表先建）
    create_sqls = [
        ("continent",    SQL_CREATE_CONTINENT),
        ("country",      SQL_CREATE_COUNTRY),
        ("station",      SQL_CREATE_STATION),
        ("aqi_history",  SQL_CREATE_AQI_HISTORY),
        ("aqi_forecast", SQL_CREATE_AQI_FORECAST),
        ("watch_list",   SQL_CREATE_WATCH_LIST),
        ("api_log",      SQL_CREATE_API_LOG),
        ("settings",          SQL_CREATE_SETTINGS),           # 系統設定（無 FK）
        ("alert_log",         SQL_CREATE_ALERT_LOG),          # 觸發事件記錄（無 FK）
        ("subscribers",       SQL_CREATE_SUBSCRIBERS),        # 訂閱會員主檔（無 FK）
        ("subscription_log",  SQL_CREATE_SUBSCRIPTION_LOG),   # 訂閱發送記錄
    ]

    try:
        conn   = get_connection()
        cursor = conn.cursor()

        # ---- 5-1. 建立資料表 ----
        for table_name, sql in create_sqls:
            cursor.execute(sql)
            logger.info(f"  [OK] 資料表 {table_name}")

        # ---- 5-2. 建立索引 ----
        for idx_sql in SQL_INDEXES:
            cursor.execute(idx_sql)
            idx_name = idx_sql.split("INDEX IF NOT EXISTS")[1].split("ON")[0].strip()
            logger.info(f"  [OK] 索引 {idx_name}")

        conn.commit()
        conn.close()
        logger.info(f"[db_init] 初始化完成 ✓  DB 路徑：{DB_PATH}")
        return True

    except sqlite3.Error as e:
        logger.error(f"[db_init] SQLite 錯誤：{e}")
        return False
    except Exception as e:
        logger.error(f"[db_init] 未預期錯誤：{e}")
        return False


# ===== 6. 取得資料表資訊（診斷用）=====

def get_table_info() -> dict:
    """
    回傳各資料表的欄位數和現有記錄數，供診斷或 UI 顯示用。
    Returns:
        dict：{ table_name: { "columns": int, "rows": int } }
    """
    tables = [
        "continent", "country", "station",
        "aqi_history", "aqi_forecast",
        "watch_list", "api_log",
        "settings", "alert_log",
        "subscribers", "subscription_log",    # ← 訂閱會員
    ]
    result = {}
    try:
        conn = get_connection()
        for t in tables:
            try:
                col_count = len(conn.execute(f"PRAGMA table_info({t})").fetchall())
                row_count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                result[t] = {"columns": col_count, "rows": row_count}
            except sqlite3.Error:
                result[t] = {"columns": 0, "rows": -1}
        conn.close()
    except Exception as e:
        logger.error(f"[db_init] get_table_info 錯誤：{e}")
    return result


# ===== 7. 直接執行時的入口 =====

if __name__ == "__main__":
    success = init_db()
    if success:
        print("\n===== 資料庫狀態 =====")
        info = get_table_info()
        for table, stat in info.items():
            print(f"  {table:<16} 欄位數：{stat['columns']:>2}  記錄數：{stat['rows']:>6}")
    else:
        print("[FAIL] 初始化失敗，請檢查 log 訊息")
