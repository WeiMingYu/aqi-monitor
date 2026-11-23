"""
pages/tab_realtime.py - 即時查詢頁籤
功能：搜尋全球監測站 → 選取站台 → 顯示詳情 → 加入監控清單
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from core.db_init    import get_conn
from core.api_client import fetch_by_city, search_stations, aqi_level


# ===== 0. 工具函數 =====

def hex_to_rgba(hex_color: str, alpha: float = 0.15) -> str:
    """
    將 #RRGGBB 轉換為 rgba(r,g,b,alpha) 字串
    plotly fillcolor 不支援 8 碼 hex（#RRGGBBAA），必須用 rgba()
    """
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ===== 1. Session State 初始化（僅此頁籤使用的狀態）=====
def _init_state():
    if "rt_search_results"   not in st.session_state: st.session_state.rt_search_results   = []
    if "rt_selected_idx"     not in st.session_state: st.session_state.rt_selected_idx     = None
    if "rt_live_data"        not in st.session_state: st.session_state.rt_live_data        = None


def render():
    """即時查詢頁籤主渲染函數，由 main.py 呼叫"""
    _init_state()

    st.header("🔍 即時空氣品質查詢")

    # ===== 2. 快速選取：台灣常用站台（uid 經 API 實際查詢確認）=====
    st.caption("🇹🇼 台灣常用站台快速選取")
    TW_STATIONS = [
        ("台北中山", "@1597"),    # Zhongshan, Taiwan (中山)
        ("新北板橋", "@1591"),    # Banqiao, Taiwan (板橋)
        ("台中",     "@12583"),   # Taichung City/Taiping
        ("高雄",     "@12909"),   # Kao-ping/CSC-F
        ("台南",     "@12593"),   # Tainan City/Chengxili
        ("基隆",     "@1586"),    # Keelung
    ]
    quick_cols = st.columns(len(TW_STATIONS))
    for col, (label, city_key) in zip(quick_cols, TW_STATIONS):
        with col:
            if st.button(label, use_container_width=True, key=f"rt_quick_{city_key}"):
                with st.spinner(f"載入 {label}..."):
                    detail = fetch_by_city(city_key)
                if detail["ok"]:
                    st.session_state.rt_live_data      = detail["data"]
                    st.session_state.rt_search_results = []
                    st.session_state.rt_selected_idx   = None
                    st.session_state.rt_error = ""
                else:
                    # rerun 會清掉畫面上的 st.error，所以錯誤訊息先存進 session_state
                    st.session_state.rt_error = f"查詢失敗（{label}）：{detail['error']}"
                st.rerun()

    # 顯示上一次快速查詢的錯誤（跨 rerun 保留）
    if st.session_state.get("rt_error"):
        st.error(st.session_state.rt_error)

    st.divider()

    # ===== 3. 搜尋列 =====
    col_kw, col_btn = st.columns([4, 1])
    with col_kw:
        keyword = st.text_input(
            "搜尋城市或監測站",
            placeholder="關鍵字（taipei）或站台ID（@5765）",
            label_visibility="collapsed",
            key="rt_keyword",
        )
    with col_btn:
        do_search = st.button("🔍 搜尋", use_container_width=True, disabled=not keyword.strip())

    # ===== 4. 執行搜尋 =====
    if do_search and keyword.strip():
        kw = keyword.strip()
        if kw.startswith("@"):
            # ===== @uid 格式：直接查詢，不走搜尋列表 =====
            with st.spinner(f"查詢 {kw}..."):
                detail = fetch_by_city(kw)
            if detail["ok"]:
                st.session_state.rt_live_data      = detail["data"]
                st.session_state.rt_search_results = []
                st.session_state.rt_selected_idx   = None
            else:
                st.error(f"查詢失敗：{detail['error']}")
        else:
            # ===== 其他任何輸入：一律走搜尋列表，讓使用者自己選 =====
            with st.spinner("搜尋中..."):
                result = search_stations(kw)
            if result["ok"] and result["stations"]:
                st.session_state.rt_search_results = result["stations"]
                st.session_state.rt_selected_idx   = None
                st.session_state.rt_live_data      = None
            else:
                st.error(f"搜尋無結果：{kw}")

    # ===== 5. 搜尋結果列表 =====
    results = st.session_state.rt_search_results
    if results:
        st.subheader(f"搜尋結果（{len(results)} 個站台）")
        for i, s in enumerate(results):
            lv, color, emoji = aqi_level(s["aqi"])
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([3, 1, 2, 1])
                with c1:
                    st.markdown(f"**{s['name']}**")
                    st.caption(f"🔑 {s['city_key']}  |  ID: @{s['uid']}")
                with c2:
                    st.markdown(f"<h2 style='color:{color};margin:0'>{s['aqi']}</h2>", unsafe_allow_html=True)
                    st.caption(f"{emoji} {lv}")
                with c3:
                    geo = s.get("geo", [None, None])
                    if geo and geo[0]:
                        st.caption(f"📍 {float(geo[0]):.3f}, {float(geo[1]):.3f}")
                with c4:
                    is_sel = (st.session_state.rt_selected_idx == i)
                    if st.button(
                        "✅ 已選取" if is_sel else "查看詳情",
                        key=f"rt_sel_{i}",
                        use_container_width=True,
                    ):
                        st.session_state.rt_selected_idx = i
                        with st.spinner("載入詳細資料..."):
                            detail = fetch_by_city(s["city_key"])
                        if detail["ok"]:
                            st.session_state.rt_live_data = detail["data"]
                        else:
                            st.error(detail["error"])
                        st.rerun()

    # ===== 5. 詳細資料顯示 =====
    d = st.session_state.rt_live_data
    if not d:
        return

    lv, color, emoji = aqi_level(d["aqi"])
    st.divider()
    st.subheader(f"📍 {d['station_name']}")
    st.caption(f"量測時間：{d.get('measure_time', 'N/A')}  |  時區：{d.get('tz', 'N/A')}")

    # AQI 大色塊
    st.markdown(
        f"<div style='background:{color}22;border-left:6px solid {color};"
        f"padding:16px;border-radius:8px;margin:8px 0'>"
        f"<h1 style='color:{color};margin:0'>{emoji} AQI {d['aqi']}</h1>"
        f"<p style='margin:4px 0;font-size:18px'>{lv}</p>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ===== 6. 各污染物數值 =====
    st.subheader("污染物即時值")
    for col, (name, val) in zip(
        st.columns(6),
        [("PM2.5", d.get("pm25")), ("PM10", d.get("pm10")), ("NO₂", d.get("no2")),
         ("CO", d.get("co")), ("SO₂", d.get("so2")), ("O₃", d.get("o3"))],
    ):
        with col:
            st.metric(name, f"{val:.1f}" if val is not None else "N/A")

    # ===== 7. 氣象資料 =====
    if any(d.get(k) is not None for k in ("temp", "humidity", "wind")):
        st.subheader("氣象資料")
        wc = st.columns(3)
        with wc[0]: st.metric("🌡️ 溫度",  f"{d['temp']:.1f} °C"   if d.get("temp")     else "N/A")
        with wc[1]: st.metric("💧 濕度",  f"{d['humidity']:.0f}%" if d.get("humidity") else "N/A")
        with wc[2]: st.metric("💨 風速",  f"{d['wind']:.1f} m/s"  if d.get("wind")     else "N/A")

    # ===== 8. 預報圖（多污染物分頁）=====
    if d.get("forecast"):
        st.subheader("📅 預報資料")

        # 今天日期（用於標記垂直線）
        from datetime import date as _date
        today_str = _date.today().strftime("%Y-%m-%d")

        # PM2.5 健康等級參考線設定
        PM25_LEVELS = [
            (15,  "#00E400", "優良"),
            (35,  "#FFFF00", "普通"),
            (54,  "#FF7E00", "敏感族群"),
            (150, "#FF0000", "不健康"),
        ]

        FORECAST_META = [
            ("pm25",  "PM2.5",   "#3B82F6"),
            ("pmp10", "PM10",    "#F59E0B"),   # ⚠️ PM10 forecast key 是 pmp10
            ("o3",    "O₃",      "#10B981"),
            ("uvi",   "UV 指數", "#8B5CF6"),
        ]
        available = [(k, l, c) for k, l, c in FORECAST_META if d["forecast"].get(k)]
        if available:
            for tab_obj, (fc_key, fc_label, fc_color) in zip(
                st.tabs([l for _, l, _ in available]), available
            ):
                with tab_obj:
                    fc_df = pd.DataFrame(d["forecast"][fc_key]).dropna(subset=["day"])
                    if fc_df.empty:
                        st.caption("無預報資料")
                        continue

                    fig = go.Figure()

                    # ---- 填色區間（min ~ max）----
                    if {"max", "min"}.issubset(fc_df.columns):
                        fig.add_trace(go.Scatter(
                            x    = pd.concat([fc_df["day"], fc_df["day"][::-1]]),
                            y    = pd.concat([fc_df["max"], fc_df["min"][::-1]]),
                            fill = "toself",
                            fillcolor = hex_to_rgba(fc_color, 0.25),  # 提高透明度，區間更明顯
                            line = dict(color="rgba(0,0,0,0)"),
                            name = "最大/最小範圍",
                            hoverinfo = "skip",
                        ))
                        # max 線（虛線）
                        fig.add_trace(go.Scatter(
                            x    = fc_df["day"],
                            y    = fc_df["max"],
                            mode = "lines",
                            line = dict(color=hex_to_rgba(fc_color, 0.5), width=1, dash="dot"),
                            name = "最大值",
                        ))
                        # min 線（虛線）
                        fig.add_trace(go.Scatter(
                            x    = fc_df["day"],
                            y    = fc_df["min"],
                            mode = "lines",
                            line = dict(color=hex_to_rgba(fc_color, 0.5), width=1, dash="dot"),
                            name = "最小值",
                        ))

                    # ---- 平均值主線 ----
                    fig.add_trace(go.Scatter(
                        x    = fc_df["day"],
                        y    = fc_df["avg"],
                        mode = "lines+markers",
                        name = "平均值",
                        line = dict(color=fc_color, width=2.5),
                        marker = dict(size=7, color=fc_color,
                                      line=dict(color="white", width=1.5)),
                    ))

                    # ---- 今天垂直標記線 ----
                    if today_str in fc_df["day"].values:
                        today_idx = fc_df["day"].tolist().index(today_str)
                        fig.add_shape(
                            type       = "line",
                            x0         = today_str, x1 = today_str,
                            y0         = 0,         y1 = 1,
                            xref       = "x",       yref = "paper",
                            line       = dict(color="rgba(255,255,255,0.5)", width=1.5, dash="dash"),
                        )
                        fig.add_annotation(
                            x         = today_str,
                            y         = 1,
                            xref      = "x", yref = "paper",
                            text      = "今天",
                            showarrow = False,
                            font      = dict(color="rgba(255,255,255,0.7)", size=11),
                            yanchor   = "bottom",
         )

                    # ---- PM2.5 健康等級參考線 ----
                    if fc_key == "pm25":
                        for yval, clr, lbl in PM25_LEVELS:
                            fig.add_hline(
                                y                   = yval,
                                line_dash           = "dot",
                                line_color          = clr,
                                opacity             = 0.5,
                                annotation_text     = lbl,
                                annotation_position = "right",
                                annotation_font_size= 10,
                            )

                    fig.update_layout(
                        height      = 320,
                        margin      = dict(l=0, r=60, t=20, b=0),
                        xaxis_title = "日期",
                        yaxis_title = fc_label,
                        legend      = dict(orientation="h", y=-0.25),
                        hovermode   = "x unified",
                        plot_bgcolor  = "rgba(0,0,0,0)",
                        paper_bgcolor = "rgba(0,0,0,0)",
                    )
                    st.plotly_chart(fig, use_container_width=True)

                    # ---- 數值表（中文欄位名）----
                    with st.expander("📋 查看數值表"):
                        show_df = fc_df[["day", "avg", "min", "max"]].copy()
                        show_df.columns = ["日期", "平均", "最小", "最大"]
                        st.dataframe(show_df, hide_index=True, use_container_width=True)

    # ===== 9. 資料來源歸因 =====
    if d.get("attributions"):
        with st.expander("📌 資料來源"):
            for attr in d["attributions"]:
                name, url = attr.get("name", ""), attr.get("url", "")
                st.markdown(f"- [{name}]({url})" if url else f"- {name}")

    # ===== 10. 加入監控清單 =====
    st.divider()
    col_name, col_add = st.columns([3, 1])
    with col_name:
        add_name = st.text_input("顯示名稱", value=d["station_name"], key="rt_add_name")
    with col_add:
        if st.button("➕ 加入監控清單", use_container_width=True):
            conn = get_conn()
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO watch_list (city_key, display_name, geo_lat, geo_lon)
                    VALUES (?, ?, ?, ?)
                """, (
                    d["city_key"], add_name,
                    d["geo"][0] if d.get("geo") else None,
                    d["geo"][1] if d.get("geo") else None,
                ))
                conn.commit()
                st.success(f"✅ 已加入：{add_name}")
            except Exception as e:
                st.error(f"加入失敗：{e}")
            finally:
                conn.close()
