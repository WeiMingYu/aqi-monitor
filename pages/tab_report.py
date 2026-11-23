"""
pages/tab_report.py - 月報產生頁籤
功能：選擇城市、月份，產生 Excel / PDF / PPT 月報下載
"""

import streamlit as st
from datetime import datetime, date
import calendar

from core.db_init import get_conn


def render():
    """月報頁籤主渲染函數"""

    # ===== 1. 頁面說明 =====
    st.header("📊 空氣品質月報")
    st.caption("選擇城市與月份，產生完整的空氣品質分析報告")

    # ===== 2. 載入監控清單 =====
    conn = get_conn()
    city_rows = conn.execute(
        "SELECT city_key, display_name FROM watch_list ORDER BY id"
    ).fetchall()
    conn.close()

    if not city_rows:
        st.info("📭 監控清單是空的，請先在「即時查詢」加入城市並累積資料。")
        return

    city_keys  = [r["city_key"]     for r in city_rows]
    city_names = [r["display_name"] for r in city_rows]

    # ===== 3. 篩選列 =====
    col_city, col_year, col_month = st.columns([3, 1.5, 1.5])

    with col_city:
        sel_names = st.multiselect(
            "選擇城市（可多選）",
            options = city_names,
            default = [city_names[0]] if city_names else [],
            key     = "report_cities",
        )

    with col_year:
        sel_year = st.selectbox(
            "年份",
            options = list(range(datetime.now().year, datetime.now().year - 3, -1)),
            key     = "report_year",
        )

    with col_month:
        sel_month = st.selectbox(
            "月份",
            options = list(range(1, 13)),
            index   = datetime.now().month - 2 if datetime.now().month > 1 else 0,
            format_func = lambda m: f"{m:02d} 月",
            key     = "report_month",
        )

    # ===== 4. 未選城市提示 =====
    if not sel_names:
        st.info("請選擇至少一個城市")
        return

    # 取得對應的 city_key
    name_to_key = dict(zip(city_names, city_keys))
    sel_keys    = [name_to_key[n] for n in sel_names]

    # ===== 5. 資料預覽（確認有資料才產生）=====
    conn = get_conn()
    placeholders = ",".join(["?"] * len(sel_keys))
    month_str    = f"{sel_year}-{sel_month:02d}"
    count_rows   = conn.execute(f"""
        SELECT w.display_name, COUNT(*) as cnt
        FROM   aqi_history h
        JOIN   watch_list   w ON h.city_key = w.city_key
        WHERE  h.city_key IN ({placeholders})
          AND  strftime('%Y-%m', h.fetch_time) = ?
        GROUP  BY h.city_key
    """, sel_keys + [month_str]).fetchall()
    conn.close()

    st.divider()

    # 資料筆數摘要
    if count_rows:
        st.subheader(f"📋 {sel_year} 年 {sel_month:02d} 月 資料預覽")
        cols = st.columns(min(len(count_rows), 4))
        for i, row in enumerate(count_rows):
            with cols[i % len(cols)]:
                st.metric(row["display_name"], f"{row['cnt']} 筆")
    else:
        st.warning(
            f"⚠️ {sel_year}/{sel_month:02d} 無資料。\n"
            "請確認排程已執行，並選擇有資料的月份。"
        )
        return

    st.divider()

    # ===== 6. 產生按鈕區 =====
    st.subheader("📥 產生月報")

    col_excel, col_pdf, col_ppt = st.columns(3)

    # ---- Excel ----
    with col_excel:
        st.markdown("**📗 Excel 分析報告**")
        st.caption("含統計摘要、每日資料、原始數據、觸發記錄")
        if st.button("產生 Excel", use_container_width=True, key="btn_excel"):
            with st.spinner("產生 Excel 中..."):
                try:
                    from reports.report_excel import generate_excel
                    excel_bytes = generate_excel(sel_keys, sel_names, sel_year, sel_month)
                    st.session_state["excel_bytes"] = excel_bytes
                    st.session_state["excel_ready"] = True
                    st.success("✅ Excel 已產生，請點下方下載")
                except Exception as e:
                    st.error(f"產生失敗：{e}")

        if st.session_state.get("excel_ready"):
            fname = f"AQI月報_{sel_year}{sel_month:02d}_{'_'.join(sel_names[:2])}.xlsx"
            st.download_button(
                "⬇️ 下載 Excel",
                data      = st.session_state["excel_bytes"],
                file_name = fname,
                mime      = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key       = "dl_excel",
                use_container_width = True,
            )

    # ---- PDF ----
    with col_pdf:
        st.markdown("**📕 PDF 會員報告**")
        st.caption("含圖表、統計摘要、專業排版，適合對外提供")
        if st.button("產生 PDF", use_container_width=True, key="btn_pdf"):
            with st.spinner("產生 PDF 中..."):
                try:
                    from reports.report_pdf import generate_pdf
                    pdf_bytes = generate_pdf(sel_keys, sel_names, sel_year, sel_month)
                    st.session_state["pdf_bytes"] = pdf_bytes
                    st.session_state["pdf_ready"] = True
                    st.success("✅ PDF 已產生，請點下方下載")
                except Exception as e:
                    st.error(f"產生失敗：{e}")

        if st.session_state.get("pdf_ready"):
            fname = f"AQI月報_{sel_year}{sel_month:02d}_{'_'.join(sel_names[:2])}.pdf"
            st.download_button(
                "⬇️ 下載 PDF",
                data      = st.session_state["pdf_bytes"],
                file_name = fname,
                mime      = "application/pdf",
                key       = "dl_pdf",
                use_container_width = True,
            )

    # ---- PPT ----
    with col_ppt:
        st.markdown("**📘 PPT 簡報**")
        st.caption("含圖表簡報，適合會議展示或會員呈現")
        if st.button("產生 PPT", use_container_width=True, key="btn_ppt"):
            with st.spinner("產生 PPT 中..."):
                try:
                    from reports.report_ppt import generate_ppt
                    ppt_bytes = generate_ppt(sel_keys, sel_names, sel_year, sel_month)
                    st.session_state["ppt_bytes"] = ppt_bytes
                    st.session_state["ppt_ready"] = True
                    st.success("✅ PPT 已產生，請點下方下載")
                except Exception as e:
                    st.error(f"產生失敗：{e}")

        if st.session_state.get("ppt_ready"):
            fname = f"AQI月報_{sel_year}{sel_month:02d}_{'_'.join(sel_names[:2])}.pptx"
            st.download_button(
                "⬇️ 下載 PPT",
                data      = st.session_state["ppt_bytes"],
                file_name = fname,
                mime      = "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                key       = "dl_ppt",
                use_container_width = True,
            )

    # ===== 7. 發送月報 =====
    st.divider()
    st.subheader("📨 發送月報")

    col_send1, col_send2 = st.columns(2)

    # ---- Email 寄送 ----
    with col_send1:
        st.markdown("**📧 Email 寄送月報**")
        st.caption("將已產生的月報附件寄送給收件人")

        # 讀取系統設定的預設收件人
        from pages.tab_settings import load_settings
        cfg = load_settings()
        default_recipients = cfg.get("email_recipients", "")

        email_to = st.text_input(
            "收件人（逗號分隔）",
            value       = default_recipients,
            placeholder = "user1@example.com, user2@example.com",
            key         = "report_email_to",
        )

        # 選擇要附加的格式
        attach_excel = st.checkbox(
            "附加 Excel", 
            value = st.session_state.get("excel_ready", False),
            disabled = not st.session_state.get("excel_ready", False),
            key = "attach_excel",
        )
        attach_pdf = st.checkbox(
            "附加 PDF",
            value = st.session_state.get("pdf_ready", False),
            disabled = not st.session_state.get("pdf_ready", False),
            key = "attach_pdf",
        )
        attach_ppt = st.checkbox(
            "附加 PPT",
            value = st.session_state.get("ppt_ready", False),
            disabled = not st.session_state.get("ppt_ready", False),
            key = "attach_ppt",
        )

        if st.button("📧 寄送月報 Email", use_container_width=True, key="btn_send_email"):
            if not email_to.strip():
                st.error("請填入收件人")
            elif not any([attach_excel, attach_pdf, attach_ppt]):
                st.error("請先產生月報，並選擇至少一種附件格式")
            else:
                with st.spinner("寄送中..."):
                    try:
                        from core.notify_email import send_report_email
                        recipients = [r.strip() for r in email_to.split(",") if r.strip()]
                        ok, msg = send_report_email(
                            city_names  = sel_names,
                            year        = sel_year,
                            month       = sel_month,
                            excel_bytes = st.session_state.get("excel_bytes") if attach_excel else None,
                            pdf_bytes   = st.session_state.get("pdf_bytes")   if attach_pdf   else None,
                            ppt_bytes   = st.session_state.get("ppt_bytes")   if attach_ppt   else None,
                            recipients  = recipients,
                        )
                        if ok:
                            st.success(f"✅ {msg}")
                        else:
                            st.error(f"寄送失敗：{msg}")
                    except Exception as e:
                        st.error(f"寄送失敗：{e}")

    # ---- LINE 通知 ----
    with col_send2:
        st.markdown("**💬 LINE 通知**")
        st.caption("發送月報完成通知到 LINE")

        # 顯示目前 LINE 設定狀態
        line_token  = cfg.get("line_channel_token", "")
        line_target = cfg.get("line_target_id", "")

        if line_token and line_target:
            st.success("🟢 LINE 已設定")
        else:
            st.warning("⚠️ LINE 未設定，請至「系統設定」填入 Token 和目標 ID")

        if st.button(
            "💬 發送 LINE 月報通知",
            use_container_width = True,
            key      = "btn_send_line",
            disabled = not (line_token and line_target),
        ):
            with st.spinner("發送中..."):
                try:
                    from core.notify_line import send_report_ready
                    ok, msg = send_report_ready(sel_names, sel_year, sel_month)
                    if ok:
                        st.success("✅ LINE 通知已發送")
                    else:
                        st.error(f"發送失敗：{msg}")
                except Exception as e:
                    st.error(f"發送失敗：{e}")

    # ===== 8. 注意事項 =====
    st.divider()
    with st.expander("ℹ️ 注意事項"):
        st.markdown("""
        - **資料來源**：WAQI 免費 API，每 30 分鐘抓取一次
        - **資料完整性**：若排程中斷，部分時段可能無資料
        - **Excel**：分析用，含原始資料，建議內部使用
        - **PDF / PPT**：會員報告用，已去除原始資料，格式專業
        - **月份選擇**：建議選擇已結束的月份，確保資料完整
        """)
