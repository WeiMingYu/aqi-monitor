"""
main.py - 全球空氣品質監測工具 入口程式
只負責：頁面設定、側邊欄控制、頁籤路由
各頁籤邏輯全部在 pages/ 資料夾下

啟動方式：python -m streamlit run main.py
"""

import os
import streamlit as st
from dotenv import load_dotenv

from core.db_init   import init_db, DEMO_MODE
from core.scheduler import start_scheduler, stop_scheduler, is_running
from pages          import tab_realtime, tab_watchlist, tab_analysis, tab_ranking
from pages          import tab_settings, tab_alert_log, tab_map, tab_report, tab_subscribers

# ===== 1. 頁面基本設定 =====
st.set_page_config(
    page_title="🌍 全球空氣品質監測",
    page_icon="🌬️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ===== 1-1. 隱藏 Streamlit 預設選單 =====
st.markdown('''
<style>
[data-testid="stSidebarNavItems"]      { display: none; }
[data-testid="stSidebarNavSeparator"] { display: none; }
</style>
''', unsafe_allow_html=True)

# ===== 2. 資料庫初始化（冪等，只有第一次會真正建表）=====
init_db()

# ===== 2-1. 展示版提示 =====
if DEMO_MODE:
    st.info("🧪 展示版：資料庫為去識別化樣本（真實空品資料、虛構訂閱會員）。"
            "排程、LINE／Email／Webhook 通知與系統設定已停用。")

# ===== 3. 啟動時載入設定（優先順序：DB > .env > 預設值）=====
def _load_initial_settings():
    """
    啟動時載入設定到 session_state。
    優先從 DB 讀取，DB 沒有才讀 .env，最後才用預設值。
    只在 session_state 尚未初始化時執行（避免每次 rerun 重覆載入）。
    """
    if st.session_state.get("_settings_loaded"):
        return

    # ---- 3-1. 先讀 .env（作為初始值備援）----
    load_dotenv()
    env_token = os.getenv("WAQI_TOKEN", "demo")

    # ---- 3-2. 從 DB 讀設定 ----
    from pages.tab_settings import load_settings, apply_settings
    db_settings = load_settings()

    # ---- 3-3a. 展示版：一律使用環境變數／Secrets 的 token，不讀也不寫 DB ----
    #      （展示 DB 內的 token 欄位是去識別化後的空值，會覆蓋掉 Secrets 的設定）
    if DEMO_MODE:
        db_settings["waqi_token"] = env_token

    # ---- 3-3. 若 DB 的 token 還是預設 demo，改用 .env 的值 ----
    if (not DEMO_MODE) and db_settings.get("waqi_token", "demo") == "demo" and env_token != "demo":
        db_settings["waqi_token"] = env_token
        # 同時寫回 DB，之後就不需要依賴 .env
        from pages.tab_settings import save_setting
        save_setting("waqi_token", env_token)

    # ---- 3-4. 套用設定到 session_state 和 api_client ----
    apply_settings(db_settings)
    st.session_state["_settings_loaded"] = True

_load_initial_settings()

# ===== 4. Session State 初始化（全域）=====
if "scheduler_msg" not in st.session_state:
    st.session_state.scheduler_msg = ""

# ===== 4-1. 自動恢復排程（Streamlit 重啟後自動恢復）=====
if (not DEMO_MODE) and not st.session_state.get("_scheduler_initialized"):
    from pages.tab_settings import load_settings as _ls
    _cfg          = _ls()
    _interval_min = int(_cfg.get("scheduler_interval", 60))
    # 排程器未啟動時自動啟動
    if not is_running():
        start_scheduler(_interval_min * 60)
        st.session_state.scheduler_msg = f"🔄 排程已自動恢復（每 {_interval_min} 分鐘）"
    st.session_state["_scheduler_initialized"] = True

# ===== 5. 側邊欄（只保留排程控制）=====
with st.sidebar:
    st.title("🌬️ AQI Monitor")
    st.caption("資料來源：World Air Quality Index（WAQI）")
    st.divider()

    # ── 排程控制 ──
    st.subheader("⏱️ 自動排程")

    interval_min = st.session_state.get("scheduler_interval", 60)
    st.caption(f"目前間隔：每 {interval_min} 分鐘（可在「系統設定」修改）")

    col_s, col_e = st.columns(2)
    with col_s:
        if st.button("▶ 啟動", use_container_width=True, disabled=is_running()):
            start_scheduler(interval_min * 60)
            st.session_state.scheduler_msg = f"✅ 排程已啟動，每 {interval_min} 分鐘"
    with col_e:
        if st.button("⏹ 停止", use_container_width=True, disabled=not is_running()):
            stop_scheduler()
            st.session_state.scheduler_msg = "🛑 排程已停止"

    # 排程狀態顯示
    if is_running():
        st.success("🟢 排程執行中")
        # 顯示下次執行時間
        from core.scheduler import get_next_run_time
        next_run = get_next_run_time()
        st.caption(f"下次執行：{next_run}")
    else:
        st.info("⚪ 排程未執行")

    if st.session_state.scheduler_msg:
        st.caption(st.session_state.scheduler_msg)

    st.divider()

    # Token 狀態提示（不顯示值，只顯示是否設定）
    token = st.session_state.get("waqi_token", "demo")
    if (not token) or token == "demo":
        st.warning("⚠️ 使用 demo token\n請至「系統設定」更新")
    else:
        st.success("🔑 API Token 已設定")

    st.divider()
    st.caption("💡 排程會定時抓取「監控清單」城市\n存入 DB 累積歷史資料")

# ===== 6. 主要頁籤路由 =====
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
    "🔍 即時查詢",
    "📋 監控清單",
    "🗺️ 地圖",
    "📈 時程分析",
    "🌐 全球排行",
    "🚨 觸發記錄",
    "📊 月報",
    "👥 訂閱會員",
    "⚙️ 系統設定",
])

with tab1: tab_realtime.render()
with tab2: tab_watchlist.render()
with tab3: tab_map.render()
with tab4: tab_analysis.render()
with tab5: tab_ranking.render()
with tab6: tab_alert_log.render()
with tab7: tab_report.render()
with tab8: tab_subscribers.render()
with tab9: tab_settings.render()
