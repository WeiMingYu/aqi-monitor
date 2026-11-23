"""
api/main.py - AQI Monitor REST API 入口
啟動：uvicorn api.main:app --host 0.0.0.0 --port 8506 --reload
文件：http://localhost:8506/docs（Swagger UI）
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

from api.routes import cities, aqi, alerts


# ===== 1. 建立 FastAPI 應用 =====
app = FastAPI(
    title       = "AQI Monitor API",
    description = "全球空氣品質監測工具 REST API，提供即時 AQI 資料、歷史趨勢、觸發記錄",
    version     = "1.0.0",
    contact     = {"name": "俞威名 WeiMing Yu", "email": ""},
)

# ===== 2. CORS 設定（允許官網、APP 跨域存取）=====
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],   # 正式部署時改為指定域名
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ===== 3. 掛載路由 =====
app.include_router(cities.router,  prefix="/api", tags=["城市清單"])
app.include_router(aqi.router,     prefix="/api", tags=["AQI 資料"])
app.include_router(alerts.router,  prefix="/api", tags=["觸發記錄"])


# ===== 4. 根路由（健康檢查）=====
@app.get("/", tags=["系統"])
def root():
    """API 健康檢查，確認服務正常運作"""
    return {
        "service":   "AQI Monitor API",
        "version":   "1.0.0",
        "status":    "ok",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "docs":      "/docs",
    }


@app.get("/api/status", tags=["系統"])
def status():
    """詳細系統狀態"""
    from core.db_init import get_table_info
    tables = get_table_info()
    return {
        "status":    "ok",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "database":  tables,
    }
