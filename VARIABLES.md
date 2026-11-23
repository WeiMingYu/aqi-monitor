# 專案變數總表
**專案：全球空氣品質監測工具（AQI Monitor）**
**路徑：** 專案根目錄
**最後更新：2026-05-07**
**規則：每次修改資料表或新增功能，同步更新此文件**

---

## 一、資料表欄位變數

### continent（洲別主檔）
| 欄位 | 類型 | 說明 |
|------|------|------|
| id | INTEGER PK | 自動遞增主鍵 |
| code | TEXT UNIQUE | 洲別代碼，如 AS / EU / AF |
| name_en | TEXT | 英文名稱 |
| name_zh | TEXT | 中文名稱 |
| sort_order | INTEGER | 排序權重 |
| is_active | INTEGER | 1=啟用 0=停用 |
| spare1/2 | TEXT | 預留文字欄 |
| spare_int1 | INTEGER | 預留整數欄 |
| spare_num1 | REAL | 預留數值欄 |

### country（國家主檔）
| 欄位 | 類型 | 說明 |
|------|------|------|
| id | INTEGER PK | 自動遞增主鍵 |
| iso2 | TEXT UNIQUE | ISO 3166-1 alpha-2，如 TW / US |
| iso3 | TEXT UNIQUE | ISO 3166-1 alpha-3，如 TWN / USA |
| name_en | TEXT | 英文名稱 |
| name_zh | TEXT | 中文名稱 |
| continent_id | INTEGER FK | → continent.id |
| timezone_default | TEXT | 預設時區，如 Asia/Taipei |
| is_active | INTEGER | 1=啟用 0=停用 |
| sort_order | INTEGER | 排序權重 |

### station（監測站主檔）
| 欄位 | 類型 | 說明 |
|------|------|------|
| uid | INTEGER PK | WAQI 官方 uid，**不自動遞增** |
| name_en | TEXT | 英文站名 |
| name_zh | TEXT | 中文站名 |
| lat | REAL | 緯度（WGS84） |
| lon | REAL | 經度（WGS84） |
| country_id | INTEGER FK | → country.id |
| admin1 | TEXT | 行政區第一層（省/州/縣市） |
| admin2 | TEXT | 行政區第二層（市/區/鄉鎮） |
| timezone | TEXT | 本地時區 |
| altitude | REAL | 海拔高度（公尺） |
| station_type | TEXT | official / unofficial / personal |
| is_active | INTEGER | 1=啟用 0=停用 |
| last_sync | TEXT | 最後同步時間（ISO8601） |

### aqi_history（AQI 歷史快照）
| 欄位 | 類型 | 說明 |
|------|------|------|
| id | INTEGER PK | 自動遞增 |
| city_key | TEXT NOT NULL | WAQI 識別碼，如 @1597 |
| station_name | TEXT | 站台名稱（冗餘存，顯示用） |
| aqi | REAL | 綜合 AQI 數值 |
| pm25 | REAL | PM2.5（μg/m³） |
| pm10 | REAL | PM10（μg/m³） |
| no2 | REAL | 二氧化氮（ppb） |
| co | REAL | 一氧化碳（ppm） |
| so2 | REAL | 二氧化硫（ppb） |
| o3 | REAL | 臭氧（ppb） |
| temp | REAL | 溫度（°C） |
| humidity | REAL | 相對濕度（%） |
| wind | REAL | 風速（m/s） |
| pressure | REAL | 氣壓（hPa） |
| measure_time | TEXT | 量測時間（ISO8601，站點當地時間） |
| fetch_time | TEXT | 系統抓取時間，DEFAULT now() |
| data_source | TEXT | waqi / openaq / manual |

### aqi_forecast（AQI 預報資料）
| 欄位 | 類型 | 說明 |
|------|------|------|
| id | INTEGER PK | 自動遞增 |
| city_key | TEXT NOT NULL | WAQI 識別碼 |
| station_uid | INTEGER | FK → station.uid，**允許 NULL** |
| pollutant | TEXT NOT NULL | pm25 / **pmp10** / o3 / uvi ⚠️ |
| forecast_day | TEXT NOT NULL | 預報日期（YYYY-MM-DD） |
| avg_val | REAL | 當日預報平均值 |
| max_val | REAL | 當日預報最大值 |
| min_val | REAL | 當日預報最小值 |
| fetch_time | TEXT | 資料抓取時間 |

### watch_list（使用者關注清單）
| 欄位 | 類型 | 說明 |
|------|------|------|
| id | INTEGER PK | 自動遞增 |
| city_key | TEXT UNIQUE | WAQI 識別碼，**不做 FK** |
| display_name | TEXT | 自訂顯示名稱 |
| geo_lat | REAL | 緯度 |
| geo_lon | REAL | 經度 |
| group_name | TEXT | 分組名稱 |
| alert_threshold | INTEGER | AQI 警戒閾值，預設 100 |
| is_active | INTEGER | 1=啟用 0=停用 |
| created_at | TEXT | 建立時間 |
| note | TEXT | 備註 |

### api_log（API 呼叫日誌）
| 欄位 | 類型 | 說明 |
|------|------|------|
| id | INTEGER PK | 自動遞增 |
| city_key | TEXT | WAQI 識別碼，**允許 NULL** |
| station_uid | INTEGER | FK → station.uid，**允許 NULL** |
| status | TEXT | ok / error / timeout / rate_limit |
| message | TEXT | 回傳訊息或錯誤說明 |
| call_time | TEXT | 呼叫時間 |

### settings（系統設定）
| key | 說明 | 預設值 |
|-----|------|--------|
| waqi_token | WAQI API Token | demo |
| webhook_url | Webhook 接收端點 URL | （空） |
| webhook_secret | Webhook 驗證密鑰 | （空） |
| alert_cooldown_hours | 同城市觸發冷卻時間（小時） | 24 |
| scheduler_interval | 排程間隔（分鐘） | 60 |

### alert_log（AQI 觸發事件記錄）
| 欄位 | 類型 | 說明 |
|------|------|------|
| id | INTEGER PK | 自動遞增 |
| city_key | TEXT NOT NULL | 觸發的城市識別碼 |
| display_name | TEXT | 城市顯示名稱（冗餘存） |
| aqi | REAL | 觸發時的 AQI 值 |
| threshold | INTEGER | 觸發時使用的閾值 |
| webhook_url | TEXT | 發送目標 URL（記錄當時設定） |
| webhook_status | TEXT | sent / skipped / failed |
| webhook_response | TEXT | Webhook 回應或錯誤訊息 |
| triggered_at | TEXT | 觸發時間 |

---

## 二、api_client.py 回傳格式變數

### fetch_by_city() / fetch_by_geo() 回傳 data 結構
| 變數名 | 類型 | 說明 |
|--------|------|------|
| city_key | str | WAQI 識別碼，如 @1597 |
| station_idx | int | WAQI 站台 idx |
| station_name | str | 站台名稱 |
| station_url | str | 站台 URL（顯示用） |
| geo | list | [lat, lon] |
| aqi | int | 綜合 AQI |
| measure_time | str | 量測時間（ISO8601） |
| tz | str | 時區字串 |
| pm25 | float\|None | PM2.5 |
| pm10 | float\|None | PM10（iaqi 裡用 pm10） |
| no2 | float\|None | 二氧化氮 |
| co | float\|None | 一氧化碳 |
| so2 | float\|None | 二氧化硫 |
| o3 | float\|None | 臭氧 |
| temp | float\|None | 溫度（iaqi key 是 t） |
| humidity | float\|None | 濕度（iaqi key 是 h） |
| wind | float\|None | 風速（iaqi key 是 w） |
| forecast | dict | 預報資料字典 |
| forecast_pm10 | list | forecast["pmp10"] 的別名 |
| forecast_uvi | list | forecast["uvi"] 的別名 |
| attributions | list | 資料來源清單 |

### search_stations() 回傳 stations 清單每筆結構
| 變數名 | 類型 | 說明 |
|--------|------|------|
| uid | int | WAQI 站台 uid |
| name | str | 站台名稱 |
| aqi | int\|str | AQI 值，**注意是字串需轉型** |
| geo | list | [lat, lon] |
| url | str | 站台 URL（顯示用） |
| city_key | str | @uid 格式，查詢用 |

---

## 三、跨模組共用變數

| 變數名 | 定義位置 | 說明 |
|--------|----------|------|
| WAQI_TOKEN | core/api_client.py | API Token，從 .env 或 settings 讀取 |
| BASE_URL | core/api_client.py | https://api.waqi.info |
| DEFAULT_INTERVAL | core/scheduler.py | 預設排程間隔，3600 秒 |
| DB_DIR | core/db_init.py | data/ 資料夾路徑 |
| DB_PATH | core/db_init.py | data/aqi_monitor.db 完整路徑 |

---

## 四、session_state key 清單

| key | 說明 | 設定位置 |
|-----|------|----------|
| waqi_token | 目前使用的 API Token | main.py / tab_settings.py |
| scheduler_interval | 排程間隔（分鐘） | tab_settings.py |
| alert_cooldown_hours | 觸發冷卻時間（小時） | tab_settings.py |
| scheduler_msg | 側邊欄排程狀態訊息 | main.py |
| _settings_loaded | 設定是否已載入（防重複） | main.py |
| rt_search_results | 即時查詢搜尋結果 | tab_realtime.py |
| rt_selected_idx | 即時查詢已選取索引 | tab_realtime.py |
| rt_live_data | 即時查詢目前顯示資料 | tab_realtime.py |
| rt_add_name | 加入監控清單的顯示名稱 | tab_realtime.py |
| wl_selected | 監控清單已勾選的 city_key 清單 | tab_watchlist.py |

---

## 五、⚠️ 重要注意事項

| 項目 | 說明 |
|------|------|
| forecast PM10 key | forecast.daily 裡 PM10 的 key 是 **pmp10**，不是 pm10 |
| search API aqi 型別 | search_stations() 回傳的 aqi 是**字串**，需 int() 轉型 |
| city_key 格式 | 一律用 **@uid** 格式（如 @1597），不用城市名稱格式 |
| Plotly fillcolor | 不支援 8 碼 hex（#RRGGBBAA），改用 **rgba()** |
| station_uid vs city_key | station 表用 uid（整數），日常操作用 city_key（@uid 字串） |
| webhook_status 值 | sent / skipped / failed（skipped = URL 未設定） |

---

## 六、檔案結構
```
iqair/
├── main.py                  # 入口，頁面設定 + 側邊欄 + tab 路由
├── .env                     # WAQI_TOKEN（啟動時讀入，之後存 settings 表）
├── core/
│   ├── db_init.py           # 資料庫初始化（本文件對應）
│   ├── api_client.py        # WAQI API 封裝
│   └── scheduler.py        # 背景排程
├── pages/
│   ├── __init__.py
│   ├── tab_realtime.py      # 即時查詢
│   ├── tab_watchlist.py     # 監控清單
│   ├── tab_analysis.py      # 時程分析
│   ├── tab_ranking.py       # 全球排行
│   └── tab_settings.py     # 系統設定
└── data/
    └── aqi_monitor.db       # SQLite 資料庫
```
