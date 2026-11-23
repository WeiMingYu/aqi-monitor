"""
pages/tab_subscribers.py - 訂閱會員管理頁籤
功能：新增/編輯/停用訂閱會員，設定訂閱方案、城市、發送時間

介面順序：
  1. 功能說明
  2. 篩選列
  3. 資料列表（含選取 button）
  4. 已選取提示
  5. 功能列（新增/編輯/刪除/啟用停用）← 在已選取後渲染，disabled 判斷準確
  6. 分隔線
  7. 沒選取且非新增模式 return
  8. 表單
  9. Email 預覽
"""

import json
import streamlit as st
from datetime import datetime

from core.db_init import get_conn


# ===== 0. 常數定義 =====
PLAN_LABELS = {
    "daily":   "📅 每日摘要",
    "weekly":  "📆 週報",
    "monthly": "📊 月報",
}

WEEKDAY_LABELS = {
    0: "週一", 1: "週二", 2: "週三", 3: "週四",
    4: "週五", 5: "週六", 6: "週日",
}


# ===== 1. Session State 初始化 =====
def _init_state():
    defaults = {
        "sub_selected": None,
        "sub_mode":     None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ===== 2. 工具函式 =====

def _get_watch_cities() -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT city_key, display_name FROM watch_list WHERE is_active = 1 ORDER BY id"
    ).fetchall()
    conn.close()
    return [{"city_key": r["city_key"], "display_name": r["display_name"]} for r in rows]


def _parse_cities(cities_json: str) -> list:
    try:
        return json.loads(cities_json or "[]")
    except Exception:
        return []


def _plan_badge(plan: str) -> str:
    return PLAN_LABELS.get(plan, plan)


def _send_schedule_text(row) -> str:
    hour = row["send_hour"] or 8
    plan = row["plan"]
    if plan == "daily":
        return f"每天 {hour:02d}:00"
    elif plan == "weekly":
        day_name = WEEKDAY_LABELS.get(row["send_weekday"] or 0, "週一")
        return f"每{day_name} {hour:02d}:00"
    elif plan == "monthly":
        return f"每月 {row['send_day'] or 1} 日 {hour:02d}:00"
    return "N/A"


# ===== 3. 主渲染函數 =====

def render():
    _init_state()

    # ===== 1. 功能說明 =====
    st.header("👥 訂閱會員管理")
    st.caption("管理空氣品質報告訂閱會員，設定訂閱方案與發送時間")

    # ===== 2. 篩選列 =====
    col_f1, col_f2, _ = st.columns([2, 2, 6])
    with col_f1:
        filter_plan = st.selectbox(
            "訂閱方案",
            ["全部", "daily", "weekly", "monthly"],
            format_func=lambda x: "全部方案" if x == "全部" else PLAN_LABELS.get(x, x),
            key="sub_filter_plan",
        )
    with col_f2:
        filter_status = st.selectbox(
            "狀態", ["全部", "啟用", "停用"],
            key="sub_filter_status",
        )

    # ===== 3. 查詢資料 =====
    where  = ["1=1"]
    params = []
    if filter_plan != "全部":
        where.append("plan = ?")
        params.append(filter_plan)
    if filter_status == "啟用":
        where.append("is_active = 1")
    elif filter_status == "停用":
        where.append("is_active = 0")

    conn = get_conn()
    rows = conn.execute(f"""
        SELECT s.*,
               (SELECT COUNT(*) FROM subscription_log l WHERE l.subscriber_id = s.id) AS sent_count
        FROM subscribers s
        WHERE {' AND '.join(where)}
        ORDER BY s.created_at DESC
    """, params).fetchall()
    conn.close()

    # ===== 4. 資料列表 =====
    if not rows:
        st.info("📭 目前無會員資料，請點「新增會員」建立第一位訂閱者。")
    else:
        st.caption(f"共 {len(rows)} 位會員")
        for row in rows:
            is_sel    = (st.session_state.sub_selected == row["id"])
            is_active = row["is_active"]
            cities    = _parse_cities(row["cities"])

            with st.container(border=True):
                c1, c2, c3, c4, c5, c6 = st.columns([0.4, 2.5, 2, 2, 1.5, 1.5])

                with c1:
                    # ---- 用 button 取代 checkbox，避免 rerun 狀態衝突 ----
                    btn_label = "✅" if is_sel else "⬜"
                    if st.button(btn_label, key=f"sub_sel_{row['id']}",
                                 use_container_width=True):
                        if is_sel:
                            # 已選取 → 點擊取消選取
                            st.session_state.sub_selected = None  # 直接清掉，不判斷 sub_mode
                            st.session_state.sub_selected = None
                        else:
                            # 未選取 → 點擊選取
                            st.session_state.sub_selected = row["id"]
                            st.session_state.sub_mode     = None
                        st.rerun()

                with c2:
                    name_color = "#1F4E79" if is_active else "#AAAAAA"
                    st.markdown(
                        f"<span style='font-weight:bold;color:{name_color}'>"
                        f"{'🟢' if is_active else '⚫'} {row['name']}</span>",
                        unsafe_allow_html=True,
                    )
                    st.caption(row["email"])

                with c3:
                    st.caption(_plan_badge(row["plan"]))
                    st.caption(_send_schedule_text(row))

                with c4:
                    st.caption(f"📍 訂閱 {len(cities)} 個城市")
                    if cities:
                        conn2 = get_conn()
                        names = []
                        for ck in cities[:2]:
                            r2 = conn2.execute(
                                "SELECT display_name FROM watch_list WHERE city_key = ?", (ck,)
                            ).fetchone()
                            names.append(r2["display_name"] if r2 else ck)
                        conn2.close()
                        suffix = f" +{len(cities)-2}" if len(cities) > 2 else ""
                        st.caption("、".join(names) + suffix)

                with c5:
                    st.caption(f"已發送 {row['sent_count']} 次")
                    st.caption(row["created_at"][:10] if row["created_at"] else "")

                with c6:
                    st.caption("✅ 啟用中" if is_active else "⏸️ 已停用")

    # ===== 5. 已選取提示 =====
    has_sel = st.session_state.sub_selected is not None
    if has_sel:
        conn = get_conn()
        sel_row = conn.execute(
            "SELECT name FROM subscribers WHERE id = ?",
            (st.session_state.sub_selected,)
        ).fetchone()
        conn.close()
        if sel_row:
            st.info(f"已選取：{sel_row['name']}")

    # ===== 6. 功能列（在已選取提示後渲染，has_sel 判斷已準確）=====
    col_add, col_edit, col_del, col_toggle, _ = st.columns([1.5, 1.5, 1.5, 1.5, 4])

    with col_add:
        if st.button("➕ 新增會員", use_container_width=True):
            st.session_state.sub_mode     = "add"
            st.session_state.sub_selected = None
            st.rerun()

    with col_edit:
        if st.button("✏️ 編輯", use_container_width=True, disabled=not has_sel):
            st.session_state.sub_mode = "edit"
            st.rerun()

    with col_del:
        if st.button("🗑️ 刪除", use_container_width=True, disabled=not has_sel):
            conn = get_conn()
            conn.execute("DELETE FROM subscribers WHERE id = ?",
                         (st.session_state.sub_selected,))
            conn.commit()
            conn.close()
            st.session_state.sub_selected = None
            st.session_state.sub_mode     = None
            st.success("已刪除會員")
            st.rerun()

    with col_toggle:
        if st.button("⏸️ 啟用/停用", use_container_width=True, disabled=not has_sel):
            conn = get_conn()
            r    = conn.execute(
                "SELECT is_active FROM subscribers WHERE id = ?",
                (st.session_state.sub_selected,)
            ).fetchone()
            if r:
                conn.execute("UPDATE subscribers SET is_active = ? WHERE id = ?",
                             (0 if r["is_active"] else 1, st.session_state.sub_selected))
                conn.commit()
            conn.close()
            st.rerun()

    # ===== 7. 分隔線 =====
    st.divider()

    # ===== 8. 沒有選取且非新增模式 return =====
    if st.session_state.sub_mode is None:
        return

    # ===== 9. 表單區域 =====
    mode   = st.session_state.sub_mode
    sel_id = st.session_state.sub_selected

    # 編輯模式：讀取現有資料
    edit_data = {}
    if mode == "edit" and sel_id:
        conn = get_conn()
        r    = conn.execute("SELECT * FROM subscribers WHERE id = ?", (sel_id,)).fetchone()
        conn.close()
        if r:
            edit_data = dict(r)

    st.subheader("➕ 新增會員" if mode == "add" else "✏️ 編輯會員")

    watch_cities     = _get_watch_cities()
    city_key_to_name = {c["city_key"]: c["display_name"] for c in watch_cities}
    city_options     = [c["city_key"] for c in watch_cities]

    # ---- 基本資料（key 含 sel_id，確保切換會員時正確渲染）----
    col_n, col_e, col_p = st.columns([2, 2, 1.5])
    with col_n:
        name = st.text_input("姓名 *", value=edit_data.get("name", ""),
                             key=f"sub_name_{sel_id}")
    with col_e:
        email = st.text_input("Email *", value=edit_data.get("email", ""),
                              key=f"sub_email_{sel_id}")
    with col_p:
        phone = st.text_input("電話（選填）", value=edit_data.get("phone", "") or "",
                              key=f"sub_phone_{sel_id}")

    # ---- 訂閱方案 ----
    plan_options = list(PLAN_LABELS.keys())
    plan_idx     = plan_options.index(edit_data.get("plan", "monthly")) if edit_data else 2
    plan = st.selectbox(
        "訂閱方案 *", plan_options, index=plan_idx,
        format_func=lambda x: PLAN_LABELS[x],
        key=f"sub_plan_{sel_id}",
    )

    # ---- 訂閱城市 ----
    existing_cities = _parse_cities(edit_data.get("cities", "[]"))
    sel_cities = st.multiselect(
        "訂閱城市 *（可多選）",
        options     = city_options,
        default     = [c for c in existing_cities if c in city_options],
        format_func = lambda k: city_key_to_name.get(k, k),
        key         = f"sub_cities_{sel_id}",
    )

    if not watch_cities:
        st.warning("監控清單是空的，請先在「即時查詢」加入城市")

    # ---- 發送時間設定 ----
    st.caption("⏰ 發送時間設定")
    col_h, col_wd, col_md = st.columns([1.5, 2, 2])

    with col_h:
        send_hour = st.number_input(
            "發送小時（0-23）",
            min_value=0, max_value=23,
            value=edit_data.get("send_hour", 8) or 8,
            key=f"sub_hour_{sel_id}",
        )
    with col_wd:
        send_weekday = st.selectbox(
            "週報：發送星期（weekly）",
            list(WEEKDAY_LABELS.keys()),
            index       = edit_data.get("send_weekday", 0) or 0,
            format_func = lambda x: WEEKDAY_LABELS[x],
            key         = f"sub_weekday_{sel_id}",
            disabled    = (plan != "weekly"),
        )
    with col_md:
        send_day = st.number_input(
            "月報：發送日期（monthly）",
            min_value=1, max_value=28,
            value=edit_data.get("send_day", 1) or 1,
            key=f"sub_day_{sel_id}",
            disabled=(plan != "monthly"),
        )

    # ---- 備註 ----
    note = st.text_area("備註（選填）", value=edit_data.get("note", "") or "",
                        height=80, key=f"sub_note_{sel_id}")

    # ---- 儲存 / 取消 ----
    col_save, col_cancel, _ = st.columns([2, 2, 6])

    with col_save:
        if st.button("💾 儲存", use_container_width=True, type="primary"):
            if not name.strip():
                st.error("請填入姓名")
                return
            if not email.strip() or "@" not in email:
                st.error("請填入有效的 Email")
                return
            if not sel_cities:
                st.error("請選擇至少一個訂閱城市")
                return

            cities_json = json.dumps(sel_cities)
            now_str     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            try:
                conn = get_conn()
                if mode == "add":
                    conn.execute("""
                        INSERT INTO subscribers
                            (name, email, phone, plan, cities,
                             send_hour, send_weekday, send_day,
                             is_active, created_at, note)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """, (name.strip(), email.strip(), phone.strip() or None,
                          plan, cities_json,
                          int(send_hour), int(send_weekday), int(send_day),
                          now_str, note.strip() or None))
                    st.success(f"✅ 已新增會員：{name}")
                else:
                    conn.execute("""
                        UPDATE subscribers SET
                            name=?, email=?, phone=?, plan=?, cities=?,
                            send_hour=?, send_weekday=?, send_day=?, note=?
                        WHERE id=?
                    """, (name.strip(), email.strip(), phone.strip() or None,
                          plan, cities_json,
                          int(send_hour), int(send_weekday), int(send_day),
                          note.strip() or None, sel_id))
                    st.success(f"✅ 已更新會員：{name}")

                conn.commit()
                conn.close()
                st.session_state.sub_mode     = None
                st.session_state.sub_selected = None
                st.rerun()

            except Exception as e:
                st.error(f"儲存失敗：{e}")

    with col_cancel:
        if st.button("✖ 取消", use_container_width=True):
            st.session_state.sub_mode     = None
            st.session_state.sub_selected = None
            st.rerun()

    # ===== 10. Email 預覽 =====
    st.divider()
    with st.expander("👁️ 預覽 Email 內容", expanded=False):
        if not sel_cities:
            st.info("請先選擇訂閱城市才能預覽")
        else:
            if st.button("🔄 產生預覽", key="btn_preview"):
                with st.spinner("產生中..."):
                    try:
                        from core.notify_daily import build_daily_html
                        conn = get_conn()
                        preview_rows = conn.execute(
                            f"SELECT city_key, display_name FROM watch_list "
                            f"WHERE city_key IN ({','.join(['?']*len(sel_cities))})",
                            sel_cities
                        ).fetchall()
                        conn.close()
                        city_names_map = {r["city_key"]: r["display_name"] for r in preview_rows}
                        html_preview   = build_daily_html(sel_cities, city_names_map)
                        st.session_state["sub_preview_html"] = html_preview
                        st.success("預覽已產生")
                    except Exception as e:
                        st.error(f"預覽失敗：{e}")

            if st.session_state.get("sub_preview_html"):
                st.caption("以下為 Email 實際顯示效果：")
                st.components.v1.html(
                    st.session_state["sub_preview_html"],
                    height    = 900,
                    scrolling = True,
                )
