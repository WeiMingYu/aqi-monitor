"""
pages/tab_analysis.py - 時程趨勢分析頁籤
功能：選城市 + 時間範圍 + 污染物 → 折線圖 + 平均圖 + CSV 匯出

時間粒度邏輯：
  - 時間範圍 <= 7 天：X 軸用 date_hour（小時粒度，如 05-08 08:00）
  - 時間範圍 >  7 天：X 軸用 date（日粒度，日平均柱狀圖）
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

from core.db_init import get_conn


def render():
    """時程分析頁籤主渲染函數"""
    st.header("📈 時程趨勢分析")

    # ===== 1. 載入監控清單（作為下拉選單來源）=====
    conn = get_conn()
    city_rows = conn.execute(
        "SELECT city_key, display_name FROM watch_list ORDER BY id"
    ).fetchall()
    conn.close()

    if not city_rows:
        st.info("請先在「監控清單」加入城市，並等待排程累積資料後再做時程分析")
        return

    # ===== 2. 篩選列 =====
    city_keys  = [r["city_key"]     for r in city_rows]
    city_names = [r["display_name"] for r in city_rows]

    col_c, col_d1, col_d2, col_p = st.columns([2.5, 1.5, 1.5, 1.5])
    with col_c:
        # multiselect 支援多城市選取
        sel_names = st.multiselect(
            "選擇城市（可多選）",
            options  = city_names,
            default  = [city_names[0]] if city_names else [],
            key      = "analysis_cities",
        )
        # 取得對應的 city_key 清單
        name_to_key = dict(zip(city_names, city_keys))
        sel_cities  = [name_to_key[n] for n in sel_names]

    with col_d1:
        date_from = st.date_input("開始日期", value=datetime.now() - timedelta(days=7))

    with col_d2:
        date_to = st.date_input("結束日期", value=datetime.now())

    with col_p:
        pollutant = st.selectbox(
            "污染物",
            ["aqi", "pm25", "pm10", "no2", "co", "so2", "o3"],
            format_func=lambda x: x.upper(),
        )

    # ===== 3. 未選城市提示 =====
    if not sel_cities:
        st.info("請選擇至少一個城市")
        return

    # ===== 4. 計算時間範圍天數（決定粒度）=====
    day_range  = (date_to - date_from).days
    use_hourly = (day_range <= 7)

    # ===== 5. 查詢所有選取城市的歷史資料 =====
    # 用 IN 一次撈全部，加上 display_name 欄位區分城市
    placeholders = ",".join(["?"] * len(sel_cities))
    conn = get_conn()
    df   = pd.read_sql_query(f"""
        SELECT h.fetch_time, h.city_key, w.display_name,
               h.aqi, h.pm25, h.pm10, h.no2, h.co, h.so2, h.o3,
               h.temp, h.humidity, h.wind, h.pressure
        FROM   aqi_history h
        JOIN   watch_list   w ON h.city_key = w.city_key
        WHERE  h.city_key       IN ({placeholders})
          AND  DATE(h.fetch_time) >= ?
          AND  DATE(h.fetch_time) <= ?
        ORDER  BY h.fetch_time
    """, conn, params=sel_cities + [str(date_from), str(date_to)])
    conn.close()

    # ===== 6. 無資料提示 =====
    if df.empty:
        st.warning("⚠️ 此時間範圍內無資料，請確認排程正在執行。")
        return

    # ===== 7. 時間欄位處理 =====
    df["fetch_time"] = pd.to_datetime(df["fetch_time"])
    df["date"]       = df["fetch_time"].dt.date
    df["hour"]       = df["fetch_time"].dt.strftime("%H:00")
    df["date_hour"]  = df["fetch_time"].dt.strftime("%m-%d %H:00")

    # ===== 8. 多城市顏色對照（最多10個城市）=====
    COLORS = [
        "#3B82F6", "#EF4444", "#10B981", "#F59E0B", "#8B5CF6",
        "#EC4899", "#06B6D4", "#84CC16", "#F97316", "#6366F1",
    ]
    city_color = {name: COLORS[i % len(COLORS)] for i, name in enumerate(sel_names)}

    # ===== 9. 統計摘要（每個城市一欄）=====
    st.caption(
        f"📅 時間範圍：{day_range} 天　　"
        f"📐 顯示粒度：{'每小時' if use_hourly else '每日平均'}　　"
        f"🏙️ 已選 {len(sel_cities)} 個城市"
    )

    if len(sel_cities) <= 4:
        cols = st.columns(len(sel_cities))
        for i, name in enumerate(sel_names):
            city_df = df[df["display_name"] == name]
            vals    = city_df[pollutant].dropna()
            with cols[i]:
                st.markdown(
                    f"<span style='color:{city_color[name]};font-weight:bold'>{name}</span>",
                    unsafe_allow_html=True,
                )
                if len(vals):
                    st.caption(
                        f"平均 {vals.mean():.1f}　"
                        f"最高 {vals.max():.1f}　"
                        f"最低 {vals.min():.1f}"
                    )
                else:
                    st.caption("無資料")

    # ===== 10. 折線圖（多城市同圖）=====
    x_col = "date_hour" if use_hourly else "fetch_time"
    x_lbl = "時間"

    fig = go.Figure()
    for name in sel_names:
        city_df = df[df["display_name"] == name].copy()
        if city_df.empty:
            continue
        fig.add_trace(go.Scatter(
            x    = city_df[x_col],
            y    = city_df[pollutant],
            mode = "lines+markers",
            name = name,
            line = dict(color=city_color[name], width=2),
            marker = dict(size=4),
        ))

    # AQI 等級參考線
    if pollutant == "aqi":
        for yval, clr, lbl in [
            (50,  "#00E400", "優良"),
            (100, "#FFFF00", "普通"),
            (150, "#FF7E00", "不健康(敏感)"),
            (200, "#FF0000", "不健康"),
        ]:
            fig.add_hline(y=yval, line_dash="dot", line_color=clr, opacity=0.5,
                          annotation_text=lbl, annotation_position="right")

    fig.update_layout(
        title  = f"{pollutant.upper()} 趨勢比較（{'每小時' if use_hourly else '每日'}）",
        height = 420,
        margin = dict(l=0, r=60, t=40, b=0),
        xaxis_title  = x_lbl,
        yaxis_title  = pollutant.upper(),
        legend       = dict(orientation="h", y=-0.15),
        hovermode    = "x unified",
        xaxis_tickangle = -45 if use_hourly else 0,
    )
    st.plotly_chart(fig, use_container_width=True)

    # ===== 11. 平均圖（多城市並排）=====
    if use_hourly:
        avg_df = df.groupby(["date_hour", "display_name"])[pollutant].mean().reset_index()
        fig2   = px.bar(
            avg_df, x="date_hour", y=pollutant, color="display_name",
            title        = f"{pollutant.upper()} 小時平均比較",
            barmode      = "group",
            color_discrete_map = city_color,
        )
        fig2.update_layout(
            height=320, margin=dict(l=0, r=0, t=40, b=0),
            xaxis_tickangle=-45,
            legend=dict(orientation="h", y=-0.25),
        )
    else:
        avg_df = df.groupby(["date", "display_name"])[pollutant].mean().reset_index()
        fig2   = px.bar(
            avg_df, x="date", y=pollutant, color="display_name",
            title        = f"{pollutant.upper()} 日平均比較",
            barmode      = "group",
            color_discrete_map = city_color,
        )
        fig2.update_layout(
            height=320, margin=dict(l=0, r=0, t=40, b=0),
            legend=dict(orientation="h", y=-0.25),
        )
    st.plotly_chart(fig2, use_container_width=True)

    # ===== 12. 熱力圖（時段 × 日期 AQI 分布）=====
    # 多城市時只取第一個城市，單城市直接使用
    heatmap_name = sel_names[0]
    heatmap_df   = df[df["display_name"] == heatmap_name].copy()

    # 熱力圖需要足夠的資料（至少 2 天 × 2 個小時）
    heatmap_df["hour_int"] = heatmap_df["fetch_time"].dt.hour
    heatmap_df["date_str"] = heatmap_df["fetch_time"].dt.strftime("%Y-%m-%d")

    if len(heatmap_df) >= 4:
        with st.expander(
            f"🌡️ 時段熱力圖 — {heatmap_name}"
            + ("（多城市時僅顯示第一個城市）" if len(sel_names) > 1 else ""),
            expanded=False,
        ):
            # 建立 pivot：行=小時(0-23)，欄=日期，值=污染物平均
            pivot = heatmap_df.pivot_table(
                index   = "hour_int",
                columns = "date_str",
                values  = pollutant,
                aggfunc = "mean",
            )

            # 補齊 0-23 所有小時（無資料顯示空白）
            all_hours = list(range(24))
            pivot = pivot.reindex(all_hours)

            # Y 軸標籤（小時）
            y_labels = [f"{h:02d}:00" for h in all_hours]

            # 顏色範圍（依污染物不同設定）
            color_ranges = {
                "aqi":  (0, 200),
                "pm25": (0, 75),
                "pm10": (0, 150),
                "no2":  (0, 100),
                "co":   (0, 5),
                "so2":  (0, 50),
                "o3":   (0, 100),
            }
            zmin, zmax = color_ranges.get(pollutant, (0, 100))
           
            fig_heat = go.Figure(go.Heatmap(
                z           = pivot.values,
                x           = pivot.columns.tolist(),
                y           = y_labels,
                colorscale  = [
                    [0.0,  "#00E400"],   # 綠：優良
                    [0.25, "#FFFF00"],   # 黃：普通
                    [0.5,  "#FF7E00"],   # 橘：敏感族群
                    [0.75, "#FF0000"],   # 紅：不健康
                    [1.0,  "#7E0023"],   # 深紅：危險
                ],
                zmin        = zmin,
                zmax        = zmax,
                hoverongaps = False,
                hovertemplate = "日期：%{x}<br>時間：%{y}<br>" + pollutant.upper() + "：%{z:.1f}<extra></extra>",
                colorbar    = dict(title=pollutant.upper()),
            ))

            fig_heat.update_layout(
                title   = f"{heatmap_name} — {pollutant.upper()} 時段分布（深色=數值高）",
                height  = 500,
                margin  = dict(l=0, r=0, t=40, b=0),
                xaxis   = dict(title="日期", side="bottom"),
                yaxis   = dict(
                    title    = "時段",
                    autorange= "reversed",   # 00:00 在最上面，符合直覺
                ),
            )
            st.plotly_chart(fig_heat, use_container_width=True)
            st.caption("💡 顏色越深表示該時段數值越高。空白格表示該時段無資料（排程未執行或資料遺漏）。")

    # ===== 13. 原始資料表 + CSV 匯出 =====
    with st.expander("📋 查看原始資料"):
        display_cols = ["fetch_time", "display_name", "date_hour", "aqi", "pm25", "pm10",
                        "no2", "co", "so2", "o3", "temp", "humidity", "wind", "pressure"]
        display_cols = [c for c in display_cols if c in df.columns and not df[c].isna().all()]
        st.dataframe(df[display_cols], use_container_width=True)
        st.download_button(
            "⬇️ 下載 CSV",
            data      = df[display_cols].to_csv(index=False, encoding="utf-8-sig"),
            file_name = f"aqi_compare_{date_from}_{date_to}.csv",
            mime      = "text/csv",
        )
