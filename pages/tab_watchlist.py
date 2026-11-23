"""
pages/tab_watchlist.py - 監控清單頁籤
功能：管理常用城市、批次抓取更新、刪除城市
      每個城市卡片可展開顯示完整污染物 + 氣象資料（從 aqi_history 最新一筆取）
"""

import streamlit as st

from core.db_init    import get_conn
from core.api_client import aqi_level
from core.scheduler  import fetch_and_save


# ===== 1. Session State 初始化 =====
def _init_state():
    if "wl_selected" not in st.session_state:
        st.session_state.wl_selected = []


def render():
    """監控清單頁籤主渲染函數"""
    _init_state()

    st.header("📋 監控城市清單")

    # ===== 2. 功能列 =====
    col_f1, col_f2, col_f3 = st.columns([2, 2, 4])

    with col_f1:
        if st.button("🔄 立即抓取所有", use_container_width=True):
            conn   = get_conn()
            cities = conn.execute("SELECT city_key, display_name FROM watch_list").fetchall()
            conn.close()
            if cities:
                prog = st.progress(0)
                msgs = []
                for i, row in enumerate(cities):
                    r = fetch_and_save(row["city_key"])
                    msgs.append(f"{'✅' if r['ok'] else '❌'} {row['display_name']}")
                    prog.progress((i + 1) / len(cities))
                st.success("\n".join(msgs))
                st.rerun()
            else:
                st.info("清單是空的，請先至「即時查詢」加入城市")

    with col_f2:
        has_sel = bool(st.session_state.wl_selected)
        if st.button("🗑️ 刪除所選", use_container_width=True, disabled=not has_sel):
            conn = get_conn()
            for city_key in st.session_state.wl_selected:
                conn.execute("DELETE FROM watch_list WHERE city_key=?", (city_key,))
            conn.commit()
            conn.close()
            st.success(f"已刪除 {len(st.session_state.wl_selected)} 個城市")
            st.session_state.wl_selected = []
            st.rerun()

    # ===== 3. 載入清單（JOIN 最新一筆歷史資料，撈所有欄位）=====
    conn = get_conn()
    rows = conn.execute("""
        SELECT w.city_key, w.display_name, w.created_at,
               h.aqi, h.pm25, h.pm10, h.no2, h.co, h.so2, h.o3,
               h.temp, h.humidity, h.wind, h.pressure,
               h.measure_time, h.fetch_time
        FROM watch_list w
        LEFT JOIN (
            SELECT city_key, aqi, pm25, pm10, no2, co, so2, o3,
                   temp, humidity, wind, pressure, measure_time, fetch_time,
                   ROW_NUMBER() OVER (PARTITION BY city_key ORDER BY fetch_time DESC) rn
            FROM aqi_history
        ) h ON w.city_key = h.city_key AND h.rn = 1
        ORDER BY w.id
    """).fetchall()
    conn.close()

    # ===== 4. 空清單提示 =====
    if not rows:
        st.info("📭 清單是空的，請至「即時查詢」搜尋並加入城市")
        return

    # ===== 5. 城市資料列表 =====
    selected_keys = st.session_state.wl_selected

    for row in rows:
        lv, color, emoji = aqi_level(row["aqi"])
        checked = row["city_key"] in selected_keys

        with st.container(border=True):

            # ---- 5-1. 主列：checkbox / 城市名 / AQI / PM2.5 / 時間 ----
            c1, c2, c3, c4, c5 = st.columns([0.4, 2.5, 1.2, 1.2, 1.8])

            with c1:
                new_checked = st.checkbox("", value=checked, key=f"wl_chk_{row['city_key']}")
                if new_checked and row["city_key"] not in selected_keys:
                    selected_keys.append(row["city_key"])
                elif not new_checked and row["city_key"] in selected_keys:
                    selected_keys.remove(row["city_key"])

            with c2:
                st.markdown(f"**{row['display_name']}**")
                st.caption(row["city_key"])

            with c3:
                # AQI 大字顯示（有資料才顯示顏色）
                if row["aqi"] is not None:
                    st.markdown(
                        f"<span style='color:{color};font-size:26px;font-weight:bold'>"
                        f"{row['aqi']}</span>",
                        unsafe_allow_html=True,
                    )
                    st.caption(f"{emoji} {lv}")
                else:
                    st.caption("尚無資料")

            with c4:
                st.metric("PM2.5", f"{row['pm25']:.1f}" if row["pm25"] is not None else "N/A")

            with c5:
                st.caption(f"最後更新：\n{row['fetch_time'] or '從未'}")

            # ---- 5-2. 展開區：完整污染物 + 氣象資料 ----
            # 只有已有資料的城市才顯示展開按鈕
            if row["aqi"] is not None:
                with st.expander("📊 查看完整資料"):

                    # ---- 污染物六欄 ----
                    st.caption("🌫️ 污染物即時值")
                    p1, p2, p3, p4, p5, p6 = st.columns(6)
                    p1.metric("PM2.5", f"{row['pm25']:.1f}"  if row["pm25"] is not None else "N/A")
                    p2.metric("PM10",  f"{row['pm10']:.1f}"  if row["pm10"] is not None else "N/A")
                    p3.metric("NO₂",   f"{row['no2']:.1f}"   if row["no2"]  is not None else "N/A")
                    p4.metric("CO",    f"{row['co']:.2f}"    if row["co"]   is not None else "N/A")
                    p5.metric("SO₂",   f"{row['so2']:.1f}"   if row["so2"]  is not None else "N/A")
                    p6.metric("O₃",    f"{row['o3']:.1f}"    if row["o3"]   is not None else "N/A")

                    # ---- 氣象三欄（有資料才顯示）----
                    has_weather = any(
                        row[k] is not None for k in ("temp", "humidity", "wind")
                    )
                    if has_weather:
                        st.caption("🌤️ 氣象資料")
                        w1, w2, w3, *_ = st.columns(6)
                        w1.metric(
                            "🌡️ 溫度",
                            f"{row['temp']:.1f} °C"   if row["temp"]     is not None else "N/A",
                        )
                        w2.metric(
                            "💧 濕度",
                            f"{row['humidity']:.0f}%" if row["humidity"] is not None else "N/A",
                        )
                        w3.metric(
                            "💨 風速",
                            f"{row['wind']:.1f} m/s"  if row["wind"]     is not None else "N/A",
                        )

                    # ---- 氣壓（單獨一行，比較少用）----
                    if row["pressure"] is not None:
                        st.caption(f"🔵 氣壓：{row['pressure']:.1f} hPa　　"
                                   f"📍 量測時間：{row['measure_time'] or 'N/A'}")

                    st.divider()

                    # ---- 警戒閾值設定 ----
                    st.caption("⚠️ 警戒閾值設定（AQI 超過此值時觸發通知）")
                    st.caption("參考：50=優良  100=普通  150=敏感族群不健康  200=不健康")

                    # 從 DB 讀目前閾值
                    conn_th = get_conn()
                    th_row  = conn_th.execute(
                        "SELECT alert_threshold FROM watch_list WHERE city_key = ?",
                        (row["city_key"],)
                    ).fetchone()
                    conn_th.close()
                    current_threshold = th_row["alert_threshold"] if th_row else 100

                    col_th, col_save = st.columns([2, 1])
                    with col_th:
                        new_threshold = st.number_input(
                            "AQI 閾值",
                            min_value        = 0,
                            max_value        = 500,
                            value            = int(current_threshold),
                            step             = 10,
                            key              = f"wl_threshold_{row['city_key']}",
                            label_visibility = "collapsed",
                        )
                    with col_save:
                        if st.button(
                            "💾 儲存閾值",
                            key                 = f"wl_save_th_{row['city_key']}",
                            use_container_width = True,
                        ):
                            conn_sv = get_conn()
                            conn_sv.execute(
                                "UPDATE watch_list SET alert_threshold = ? WHERE city_key = ?",
                                (new_threshold, row["city_key"]),
                            )
                            conn_sv.commit()
                            conn_sv.close()
                            st.success(f"✅ 閾值已更新為 {new_threshold}")

    # ===== 6. 更新 session_state =====
    st.session_state.wl_selected = selected_keys
