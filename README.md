# 全球空氣品質監測平台（AQI Monitor）

串接 [WAQI](https://aqicn.org) 開放資料，定時抓取監控測站的空氣品質並累積歷史；超過警戒值時自動記錄並以 LINE／Email 通知，另有管理後台、對外 REST API、月報輸出與訂閱發信。

這是我為了配合行銷使用（以空氣品質警報作為廣告推出時機的依據）而自行發想並獨立開發的個人專案，**不是教學範例**：自 2026/05 起實際運作。

## 實際運作數據（正式環境，截至 2026/11/23）

| 項目 | 數字 |
|------|------|
| 有資料的天數 | 196 天 |
| 即時快照 | 約 6.3 萬筆 |
| 預報資料 | 約 130 萬筆 |
| 監控測站 | 7 個（新北市） |
| 警報觸發紀錄 | 37 筆 |
| 每日摘要 Email（訂閱發送） | 188 筆成功 |
| 排程間隔 | 每 30 分鐘 |

> 服務依附在我自己的電腦上，關機期間沒有資料，所以紀錄中有數段空白，並非系統錯誤。

## 這個 repo 的展示版

`data/demo/aqi_monitor.db` 是去識別化的展示資料庫：

- 保留最近 30 天的真實空品資料（公開資料）。
- 訂閱會員為虛構的 `demo@example.com`，所有 Token、密碼、Email 設定皆為空。
- 設定 `AQI_DEMO_MODE=1` 後：停用排程、停用 LINE／Email／Webhook 通知、隱藏系統設定頁。

### 快速開始（展示版）

```bash
pip install -r requirements.txt
# Windows PowerShell:  $env:AQI_DEMO_MODE = "1"
# macOS / Linux:       export AQI_DEMO_MODE=1
python -m streamlit run main.py
```

「即時查詢」頁需要 WAQI Token 才能查詢任意測站：複製 `.env.example` 為 `.env`，填入自己的 Token（`.env` 已被 `.gitignore` 排除）。免費申請：<https://aqicn.org/data-platform/token/>

### 正式模式

不設定 `AQI_DEMO_MODE`，程式會在 `data/` 建立自己的資料庫；在「系統設定」填入 WAQI Token，以及需要的 LINE、Email、Webhook 設定。

## 功能

- **管理後台（Streamlit，9 個頁籤）**：即時查詢、監控清單、地圖、時程分析、全球排行、觸發記錄、月報、訂閱會員、系統設定。
- **警報通知**：AQI 超過閾值觸發，寫入 `alert_log`；LINE Messaging API 與 SMTP Email 雙通道；同一城市有冷卻時間（預設 24 小時）避免重複通知。
- **REST API（FastAPI，10 個端點）**：城市清單、最新 AQI、歷史、今日摘要、觸發紀錄與統計，附 Swagger 文件（`/docs`）。
- **月報**：自動產生 Excel、PDF、PPT。
- **訂閱會員**：每日摘要 HTML Email 批次發送與發送紀錄。
- **維運**：`health_check.py` 9 項健康檢查。

## 架構

```
WAQI API ──► core/api_client.py ──► core/scheduler.py (APScheduler, 30 分鐘)
                                        │
                      ┌─────────────────┼──────────────────┐
                      ▼                 ▼                  ▼
                SQLite (11 表)     警報判斷＋冷卻      每日摘要發送
                      ▲                 │                  │
        ┌─────────────┤          LINE / Email / Webhook    Email
        │             │
  Streamlit 後台   FastAPI REST API (port 8506) ──► 網站 widget / APP
  (pages/*.py)     (api/)
```

主要目錄：`core/`（資料庫、API 封裝、排程、通知）、`pages/`（各頁籤）、`api/`（REST）、`reports/`（Excel／PDF／PPT）。完整欄位說明見 [VARIABLES.md](VARIABLES.md)。

## 設計重點

- **先定資料結構再開發**：每張表預留 `spare` 欄位（文字、整數、數值），需求變更時不必改表。
- **`city_key` 一律使用 `@uid` 格式**：測站名稱不是穩定的查詢鍵。
- **踩過的 API 坑**，記錄在專案文件與程式註解：
  - 預報裡 PM10 的 key 是 `pmp10`，不是 `pm10`。
  - 搜尋 API 回傳的 `aqi` 是字串（可能是 `"-"`），需轉型。
  - Plotly 的 `fillcolor` 不支援 8 碼 hex，要改用 `rgba()`。
- **機密不進程式碼**：Token 放 `.env`，展示庫全部清空。

## 已知限制與改進計畫

我把限制寫出來，是因為這些是我清楚知道、也打算處理的事：

1. **排程依附 Streamlit 行程**：後台關閉排程就停止。改進方向：拆成獨立背景服務，或使用系統服務／工作排程器常駐。
2. **REST API 沒有驗證**，且 CORS 設為 `*`。正式對外前必須加 API Key 並限制來源。
3. **機密以明文存在 `settings` 資料表**（LINE Token、SMTP 密碼）。改進方向：改用環境變數或加密儲存。
4. **洲別／國家／測站主檔表已建立但尚未匯入資料**，目前以監控清單的 `city_key` 運作。
5. **Webhook 通知已實作，但我沒有實際使用過**，不宣稱已驗證；LINE 與 Email 則已長期實際使用。
6. **PDF 月報的中文字型路徑寫死為 Windows 字型**，在 Linux／雲端需要改成可設定。
7. 尚未有自動化測試。

## 資料來源

空氣品質資料來自 [World Air Quality Index Project](https://aqicn.org)，使用請遵守其服務條款與標示要求。

## 授權

個人練習專案，尚未指定授權。
