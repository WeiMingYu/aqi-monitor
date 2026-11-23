"""
pages/tab_map.py - 地圖顯示頁籤
功能：監控清單城市在地圖上顯示，依 AQI 等級著色
      點擊站點可查看詳細資料
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from core.db_init    import get_conn
from core.api_client import aqi_level


# ===== 1. AQI 等級顏色對照（給 Plotly 用的 RGB 格式）=====
def _aqi_color(aqi_val) -> str:
    """
    依 AQI 值回傳顏色字串（rgba 格式，Plotly scatter_mapbox 用）
    """
    try:
        v = float(aqi_val)
    except (TypeError, ValueError):
        return "rgba(150,150,150,0.8)"   # 灰色：無資料

    if v <= 50:   return "rgba(0,228,0,0.85)"       # 綠：優良
    if v <= 100:  return "rgba(255,255,0,0.85)"      # 黃：普通
    if v <= 150:  return "rgba(255,126,0,0.85)"      # 橘：敏感族群不健康
    if v <= 200:  return "rgba(255,0,0,0.85)"        # 紅：不健康
    if v <= 300:  return "rgba(143,63,151,0.85)"     # 紫：非常不健康
    return             "rgba(126,0,35,0.85)"          # 深紅：危險


def render():
    """地圖頁籤主渲染函數"""

    # ===== 1. 頁面說明 =====
    st.header("🗺️ 監控城市地圖")
    st.caption("監控清單城市的即時 AQI 分布，顏色對應空氣品質等級")

    # ===== 2. 查詢資料（watch_list JOIN 最新一筆 aqi_history）=====
    conn = get_conn()
    df   = pd.read_sql_query("""
        SELECT w.city_key, w.display_name, w.geo_lat, w.geo_lon,
               h.aqi, h.pm25, h.pm10, h.fetch_time
        FROM watch_list w
        LEFT JOIN (
            SELECT city_key, aqi, pm25, pm10, fetch_time,
                   ROW_NUMBER() OVER (PARTITION BY city_key ORDER BY fetch_time DESC) rn
            FROM aqi_history
        ) h ON w.city_key = h.city_key AND h.rn = 1
        WHERE w.geo_lat IS NOT NULL AND w.geo_lon IS NOT NULL
        ORDER BY w.id
    """, conn)
    conn.close()

    # ===== 3. 無資料提示 =====
    if df.empty:
        st.info("📭 監控清單是空的，或城市尚無座標資料。請先在「即時查詢」加入城市。")
        return

    # ===== 4. 計算地圖中心（取所有城市座標平均）=====
    center_lat = df["geo_lat"].mean()
    center_lon = df["geo_lon"].mean()

    # ===== 5. 準備每個點的顏色、大小、hover 文字 =====
    df["color"]      = df["aqi"].apply(_aqi_color)
    df["aqi_lv"]     = df["aqi"].apply(lambda x: aqi_level(x)[0])
    df["aqi_emoji"]  = df["aqi"].apply(lambda x: aqi_level(x)[2])
    df["marker_size"]= df["aqi"].apply(
        # AQI 越高點越大，最小 14，最大 36
        lambda x: min(36, max(14, int(float(x) / 8)))
        if pd.notna(x) else 14   # ← 用 pd.notna() 取代 is not None
    )
    df["hover_text"] = df.apply(lambda r: (
    f"<b>{r['display_name']}</b><br>"
    f"AQI：{int(r['aqi']) if pd.notna(r['aqi']) else 'N/A'}  {r['aqi_emoji']} {r['aqi_lv']}<br>"
    f"PM2.5：{str(round(r['pm25'], 1)) if pd.notna(r['pm25']) else 'N/A'}<br>"
    f"PM10：{str(round(r['pm10'], 1)) if pd.notna(r['pm10']) else 'N/A'}<br>"
    f"更新：{r['fetch_time'] or '從未'}"
), axis=1)

    # ===== 6. 統計摘要列 =====
    has_data  = df[df["aqi"].notna()]
    no_data   = df[df["aqi"].isna()]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📍 監控城市",  len(df))
    col2.metric("✅ 有資料",    len(has_data))
    col3.metric("⚠️ 無資料",    len(no_data))
    if len(has_data):
        col4.metric("📊 平均 AQI", f"{has_data['aqi'].mean():.0f}")
    else:
        col4.metric("📊 平均 AQI", "N/A")

    # ===== 7. AQI 等級圖例 =====
    st.markdown(
        "**等級說明：**　"
        "🟢 0-50 優良　"
        "🟡 51-100 普通　"
        "🟠 101-150 敏感族群不健康　"
        "🔴 151-200 不健康　"
        "🟣 201-300 非常不健康　"
        "⚫ 300+ 危險　"
        "⬜ 無資料"
    )

    # ===== 8. 建立地圖 =====
    fig = go.Figure()

    # ---- 8-1. 有 AQI 資料的城市 ----
    if len(has_data):
        fig.add_trace(go.Scattermapbox(
            lat        = has_data["geo_lat"].tolist(),
            lon        = has_data["geo_lon"].tolist(),
            mode       = "markers+text",
            marker     = go.scattermapbox.Marker(
                size       = has_data["marker_size"].tolist(),
                color      = has_data["color"].tolist(),
                opacity    = 0.9,
            ),
            text       = has_data["display_name"].tolist(),
            textposition = "top center",
            textfont   = dict(size=11, color="white"),
            hovertext  = has_data["hover_text"].tolist(),
            hoverinfo  = "text",
            name       = "監控城市",
        ))

    # ---- 8-2. 無資料的城市（灰色小點）----
    if len(no_data):
        fig.add_trace(go.Scattermapbox(
            lat        = no_data["geo_lat"].tolist(),
            lon        = no_data["geo_lon"].tolist(),
            mode       = "markers+text",
            marker     = go.scattermapbox.Marker(
                size    = 12,
                color   = "rgba(150,150,150,0.6)",
            ),
            text       = no_data["display_name"].tolist(),
            textposition = "top center",
            textfont   = dict(size=10, color="#AAAAAA"),
            hovertext  = no_data["display_name"].apply(
                lambda n: f"<b>{n}</b><br>尚無資料"
            ).tolist(),
            hoverinfo  = "text",
            name       = "尚無資料",
        ))

    # ===== 9. 地圖版面設定 =====
    fig.update_layout(
        mapbox = dict(
            style  = "open-street-map",   # 免費，不需要 token
            center = dict(lat=center_lat, lon=center_lon),
            zoom   = 9,                   # 台灣適合 9，全球監控可調低
        ),
        margin      = dict(l=0, r=0, t=0, b=0),
        height      = 560,
        showlegend  = False,
        paper_bgcolor = "rgba(0,0,0,0)",
    )

    st.plotly_chart(fig, use_container_width=True)

    # ===== 10. 城市列表（地圖下方）=====
    st.divider()
    st.subheader("📋 城市 AQI 列表")

    # 依 AQI 排序（高到低），無資料排最後
    df_sorted = pd.concat([
        has_data.sort_values("aqi", ascending=False),
        no_data,
    ]).reset_index(drop=True)

    for _, row in df_sorted.iterrows():
        lv, color, emoji = aqi_level(row["aqi"])
        c1, c2, c3, c4, c5 = st.columns([2.5, 1, 1, 1, 2])
        with c1:
            st.markdown(f"**{row['display_name']}**")
            st.caption(row["city_key"])
        with c2:
            if pd.notna(row["aqi"]):
                st.markdown(
                    f"<span style='color:{color};font-size:22px;font-weight:bold'>"
                    f"{int(row['aqi'])}</span>",
                    unsafe_allow_html=True,
                )
            else:
                st.caption("N/A")
        with c3:
            st.caption(f"{emoji} {lv}")
        with c4:
            st.metric("PM2.5", f"{row['pm25']:.1f}" if pd.notna(row['pm25']) else "N/A",
                      label_visibility="collapsed")
        with c5:
            st.caption(f"更新：{row['fetch_time'] or '從未'}")
