"""
pages/tab_ranking.py - 全球排行頁籤
功能：監控清單城市最新 AQI 橫向比較
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from core.db_init    import get_conn
from core.api_client import aqi_level


def render():
    """全球排行頁籤主渲染函數"""
    st.header("🌐 監控城市 AQI 排行")

    # ===== 1. 查詢每個城市最新一筆資料 =====
    conn = get_conn()
    df   = pd.read_sql_query("""
        SELECT w.display_name, w.city_key,
               h.aqi, h.pm25, h.pm10, h.fetch_time
        FROM watch_list w
        LEFT JOIN (
            SELECT city_key, aqi, pm25, pm10, fetch_time,
                   ROW_NUMBER() OVER (PARTITION BY city_key ORDER BY fetch_time DESC) rn
            FROM aqi_history
        ) h ON w.city_key = h.city_key AND h.rn = 1
        WHERE h.aqi IS NOT NULL
        ORDER BY h.aqi DESC
    """, conn)
    conn.close()

    # ===== 2. 無資料提示 =====
    if df.empty:
        st.info("尚無資料。請先加入城市到監控清單，執行一次抓取後再查看。")
        return

    # ===== 3. 加入等級與顏色欄位 =====
    df["level"] = df["aqi"].apply(lambda x: aqi_level(x)[0])
    df["color"] = df["aqi"].apply(lambda x: aqi_level(x)[1])

    # ===== 4. 橫向 AQI 長條圖 =====
    fig = go.Figure(go.Bar(
        y=df["display_name"],
        x=df["aqi"],
        orientation="h",
        marker_color=df["color"],
        text=df["aqi"],
        textposition="outside",
    ))
    fig.update_layout(
        title="各城市 AQI 比較（最新一筆）",
        height=max(300, len(df) * 50),
        xaxis_title="AQI",
        yaxis=dict(autorange="reversed"),
        margin=dict(l=0, r=60, t=50, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ===== 5. 資料表 =====
    display = df[["display_name", "aqi", "level", "pm25", "fetch_time"]].copy()
    display.columns = ["城市", "AQI", "等級", "PM2.5", "最後更新"]
    st.dataframe(display, use_container_width=True, hide_index=True)
