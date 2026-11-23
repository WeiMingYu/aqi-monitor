"""
pages/tab_alert_log.py - AQI 觸發事件記錄頁籤
功能：顯示 AQI 超閾值觸發記錄、Webhook 發送狀態、統計摘要
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from core.db_init import get_conn


def render():
    """觸發事件記錄頁籤主渲染函數"""

    # ===== 1. 頁面說明 =====
    st.header("🚨 AQI 觸發事件記錄")
    st.caption("顯示 AQI 超閾值的觸發事件，以及 Webhook 發送狀態")

    # ===== 2. 功能列（篩選條件）=====
    col_city, col_status, col_d1, col_d2 = st.columns([2, 1.5, 1.5, 1.5])

    # ---- 城市選單（從 alert_log 取已觸發過的城市）----
    conn = get_conn()
    city_rows = conn.execute("""
        SELECT DISTINCT city_key, display_name
        FROM   alert_log
        ORDER  BY display_name
    """).fetchall()
    conn.close()

    city_options = {"全部": None}
    for r in city_rows:
        city_options[r["display_name"] or r["city_key"]] = r["city_key"]

    with col_city:
        sel_city_label = st.selectbox("城市", list(city_options.keys()), key="al_city")
        sel_city_key   = city_options[sel_city_label]

    with col_status:
        sel_status = st.selectbox(
            "Webhook 狀態",
            ["全部", "sent", "skipped", "failed"],
            key="al_status",
        )

    with col_d1:
        date_from = st.date_input(
            "開始日期",
            value=datetime.now() - timedelta(days=30),
            key="al_date_from",
        )

    with col_d2:
        date_to = st.date_input(
            "結束日期",
            value=datetime.now(),
            key="al_date_to",
        )

    # ===== 3. 查詢資料 =====
    conn = get_conn()

    # 動態組合 WHERE 條件
    where_clauses = ["DATE(triggered_at) >= ?", "DATE(triggered_at) <= ?"]
    params        = [str(date_from), str(date_to)]

    if sel_city_key:
        where_clauses.append("city_key = ?")
        params.append(sel_city_key)

    if sel_status != "全部":
        where_clauses.append("webhook_status = ?")
        params.append(sel_status)

    where_sql = " AND ".join(where_clauses)

    df = pd.read_sql_query(f"""
        SELECT id, triggered_at, display_name, city_key,
               aqi, threshold, webhook_status, webhook_response, webhook_url
        FROM   alert_log
        WHERE  {where_sql}
        ORDER  BY triggered_at DESC
    """, conn, params=params)
    conn.close()

    # ===== 4. 無資料提示 =====
    if df.empty:
        st.info("📭 此條件下無觸發記錄。AQI 超過監控清單設定的閾值時才會產生記錄。")
        return

    # ===== 5. 統計摘要 =====
    total   = len(df)
    sent    = len(df[df["webhook_status"] == "sent"])
    skipped = len(df[df["webhook_status"] == "skipped"])
    failed  = len(df[df["webhook_status"] == "failed"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📋 總觸發次數", total)
    c2.metric("📤 已發送",     sent,    delta=None)
    c3.metric("📝 僅記錄",     skipped, delta=None)
    c4.metric("❌ 發送失敗",   failed,  delta=None)

    st.divider()

    # ===== 6. 資料列表 =====
    for _, row in df.iterrows():

        # 依 webhook_status 決定卡片左邊框顏色
        status_color = {
            "sent":    "#10B981",   # 綠色
            "skipped": "#6B7280",   # 灰色
            "failed":  "#EF4444",   # 紅色
        }.get(row["webhook_status"], "#6B7280")

        status_emoji = {
            "sent":    "📤 已發送",
            "skipped": "📝 僅記錄",
            "failed":  "❌ 發送失敗",
        }.get(row["webhook_status"], row["webhook_status"])

        # AQI 超閾值幅度
        over = int(row["aqi"]) - int(row["threshold"]) if row["aqi"] and row["threshold"] else 0

        with st.container(border=True):
            st.markdown(
                f"<div style='border-left:4px solid {status_color};padding-left:10px'>",
                unsafe_allow_html=True,
            )

            c1, c2, c3, c4 = st.columns([2.5, 1.2, 1.2, 2.5])
            with c1:
                st.markdown(f"**{row['display_name'] or row['city_key']}**")
                st.caption(f"🕐 {row['triggered_at']}")
            with c2:
                st.metric(
                    "AQI",
                    int(row["aqi"]) if row["aqi"] else "N/A",
                    delta=f"+{over} 超標" if over > 0 else None,
                    delta_color="inverse",
                )
            with c3:
                st.metric("閾值", int(row["threshold"]) if row["threshold"] else "N/A")
            with c4:
                st.markdown(f"**{status_emoji}**")
                if row["webhook_response"] and row["webhook_response"] != "skipped":
                    st.caption(f"回應：{row['webhook_response']}")

            st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    # ===== 7. 清除記錄 =====
    with st.expander("🗑️ 清除記錄（謹慎操作）"):
        st.warning("清除後無法復原，請確認後再操作。")
        col_clr1, col_clr2, _ = st.columns([2, 2, 4])

        with col_clr1:
            # 清除目前篩選範圍的記錄
            if st.button("清除目前篩選範圍", use_container_width=True):
                conn = get_conn()
                conn.execute(f"DELETE FROM alert_log WHERE {where_sql}", params)
                conn.commit()
                conn.close()
                st.success("已清除篩選範圍內的記錄")
                st.rerun()

        with col_clr2:
            # 清除全部記錄
            if st.button("清除全部記錄", use_container_width=True, type="primary"):
                conn = get_conn()
                conn.execute("DELETE FROM alert_log")
                conn.commit()
                conn.close()
                st.success("已清除全部觸發記錄")
                st.rerun()
