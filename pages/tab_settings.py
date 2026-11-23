"""
pages/tab_settings.py - 系統設定頁籤
功能：集中管理所有系統設定，分類顯示
分類：WAQI API / 排程與觸發 / Webhook / LINE 通知 / Email 設定
設定存入 settings 資料表，啟動時自動載入
"""

import streamlit as st
import requests
import smtplib
from datetime import datetime
from email.mime.text import MIMEText

from core.db_init import get_conn


# ===== 1. 設定鍵值定義（集中管理）=====
SETTING_KEYS = {
    # WAQI
    "waqi_token":           {"label": "WAQI API Token",           "default": "demo",           "type": "password"},
    # 排程
    "scheduler_interval":   {"label": "排程間隔（分鐘）",         "default": "60",             "type": "number"},
    "alert_cooldown_hours": {"label": "觸發冷卻時間（小時）",     "default": "24",             "type": "number"},
    # Webhook
    "webhook_url":          {"label": "Webhook URL",               "default": "",               "type": "text"},
    "webhook_secret":       {"label": "Webhook Secret",            "default": "",               "type": "password"},
    # LINE
    "line_channel_token":   {"label": "LINE Channel Access Token", "default": "",               "type": "password"},
    "line_target_id":       {"label": "LINE 推播目標 ID",          "default": "",               "type": "text"},
    # Email
    "email_smtp_host":      {"label": "SMTP 主機",                 "default": "smtp.gmail.com", "type": "text"},
    "email_smtp_port":      {"label": "SMTP 埠",                   "default": "587",            "type": "number"},
    "email_account":        {"label": "寄件帳號",                  "default": "",               "type": "text"},
    "email_password":       {"label": "寄件密碼 / App Password",   "default": "",               "type": "password"},
    "email_recipients":     {"label": "預設收件人（逗號分隔）",    "default": "",               "type": "text"},
}


# ===== 2. 從 DB 讀取所有設定 =====
def load_settings() -> dict:
    """從 settings 資料表讀取所有設定值，不存在則回傳預設值"""
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()

    result = {k: v["default"] for k, v in SETTING_KEYS.items()}
    for row in rows:
        if row["key"] in result:
            result[row["key"]] = row["value"]
    return result


# ===== 3. 儲存單一設定 =====
def save_setting(key: str, value: str) -> bool:
    """將設定值寫入 settings 資料表（INSERT OR REPLACE）"""
    try:
        conn = get_conn()
        conn.execute("""
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value      = excluded.value,
                updated_at = excluded.updated_at
        """, (key, value, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"儲存失敗：{e}")
        return False


# ===== 4. 同步設定到 session_state 和各模組 =====
def apply_settings(settings: dict):
    """將設定值同步到 session_state 及相關模組（不需重啟）"""
    token = settings.get("waqi_token", "demo")
    st.session_state["waqi_token"] = token
    try:
        from core import api_client as _ac
        _ac.WAQI_TOKEN = token
    except Exception:
        pass

    st.session_state["scheduler_interval"]   = int(settings.get("scheduler_interval", 60))
    st.session_state["alert_cooldown_hours"] = int(settings.get("alert_cooldown_hours", 24))


# ===== 5. 測試函式 =====

def test_waqi_token(token: str) -> tuple:
    """測試 WAQI Token 是否有效"""
    try:
        url  = f"https://api.waqi.info/feed/@1597/?token={token}"
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if data.get("status") == "ok":
            aqi = data["data"].get("aqi", "N/A")
            return True, f"連線成功！台北中山站目前 AQI：{aqi}"
        else:
            return False, f"Token 無效：{data.get('data', 'Unknown error')}"
    except Exception as e:
        return False, f"連線失敗：{e}"


def test_webhook(url: str, secret: str) -> tuple:
    """發送測試訊號到 Webhook URL"""
    if not url.strip():
        return False, "請先填入 Webhook URL"
    try:
        payload = {
            "event":     "test",
            "message":   "AQI Monitor Webhook 測試訊號",
            "timestamp": datetime.now().isoformat(),
        }
        headers = {"Content-Type": "application/json"}
        if secret:
            headers["X-Webhook-Secret"] = secret
        resp = requests.post(url, json=payload, headers=headers, timeout=5)
        if resp.status_code in (200, 201, 204):
            return True, f"Webhook 測試成功（HTTP {resp.status_code}）"
        else:
            return False, f"Webhook 回應異常（HTTP {resp.status_code}）"
    except Exception as e:
        return False, f"連線失敗：{e}"


def test_line(token: str, target_id: str) -> tuple:
    """發送測試訊息到 LINE Messaging API"""
    if not token.strip():
        return False, "請先填入 Channel Access Token"
    if not target_id.strip():
        return False, "請先填入推播目標 ID"
    try:
        url     = "https://api.line.me/v2/bot/message/push"
        headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {token}",
        }
        payload = {
            "to":       target_id,
            "messages": [{"type": "text", "text": "✅ AQI Monitor LINE 通知測試成功！"}],
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=5)
        if resp.status_code == 200:
            return True, "LINE 測試訊息發送成功"
        else:
            return False, f"LINE API 錯誤（HTTP {resp.status_code}）：{resp.text[:200]}"
    except Exception as e:
        return False, f"連線失敗：{e}"


def test_email(host: str, port: int, account: str, password: str, recipients: str) -> tuple:
    """測試 Email SMTP 連線並發送測試信"""
    if not account.strip() or not password.strip():
        return False, "請先填入寄件帳號和密碼"
    if not recipients.strip():
        return False, "請先填入收件人"
    try:
        server = smtplib.SMTP(host, int(port), timeout=10)
        server.ehlo()
        server.starttls()
        server.login(account, password)

        msg            = MIMEText("這是 AQI Monitor 的 Email 測試信件，收到表示設定正確。", "plain", "utf-8")
        msg["Subject"] = "AQI Monitor Email 測試"
        msg["From"]    = account
        msg["To"]      = recipients.split(",")[0].strip()

        server.sendmail(account, [recipients.split(",")[0].strip()], msg.as_string())
        server.quit()
        return True, f"測試信發送成功（收件人：{recipients.split(',')[0].strip()}）"
    except Exception as e:
        return False, f"Email 連線失敗：{e}"


# ===== 6. 主渲染函數 =====
def render():
    from core.db_init import DEMO_MODE
    if DEMO_MODE:
        st.info("展示版不開放系統設定（含 Token、Email、LINE 等機密欄位）。")
        return
    """系統設定頁籤主渲染函數"""

    st.header("⚙️ 系統設定")
    current = load_settings()

    # =====================================================
    # 區塊一：WAQI API 設定
    # =====================================================
    st.subheader("📡 WAQI API 設定")

    col_token, col_test = st.columns([4, 1])
    with col_token:
        new_token = st.text_input(
            "WAQI API Token",
            value = current["waqi_token"],
            type  = "password",
            help  = "至 https://aqicn.org/data-platform/token/ 免費申請",
            key   = "cfg_waqi_token",
        )
    with col_test:
        st.write("")
        st.write("")
        if st.button("🔌 測試", use_container_width=True, key="test_waqi"):
            with st.spinner("測試中..."):
                ok, msg = test_waqi_token(new_token)
            st.success(msg) if ok else st.error(msg)

    if new_token == "demo":
        st.warning("⚠️ 目前使用 demo token，僅支援少數城市，建議申請正式 token")

    st.divider()

    # =====================================================
    # 區塊二：排程與觸發設定
    # =====================================================
    st.subheader("⏱️ 排程與觸發設定")

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        new_interval = st.number_input(
            "排程間隔（分鐘）",
            min_value = 5,
            max_value = 1440,
            value     = int(current["scheduler_interval"]),
            step      = 5,
            help      = "每隔幾分鐘自動抓取監控清單城市資料",
            key       = "cfg_interval",
        )
    with col_s2:
        new_cooldown = st.number_input(
            "觸發冷卻時間（小時）",
            min_value = 1,
            max_value = 168,
            value     = int(current["alert_cooldown_hours"]),
            step      = 1,
            help      = "同一城市觸發後，幾小時內不重複發送通知",
            key       = "cfg_cooldown",
        )

    st.divider()

    # =====================================================
    # 區塊三：Webhook 設定
    # =====================================================
    st.subheader("📤 Webhook 設定")
    st.caption("AQI 超標時自動 POST 事件到指定 URL，供公司 APP 或官網串接")

    new_webhook_url = st.text_input(
        "Webhook URL",
        value       = current["webhook_url"],
        placeholder = "https://your-app.com/api/aqi-alert",
        help        = "POST 接收端點，留空則只記錄不發送",
        key         = "cfg_webhook_url",
    )
    new_webhook_secret = st.text_input(
        "Webhook Secret（選填）",
        value = current["webhook_secret"],
        type  = "password",
        help  = "驗證用，放在 Header X-Webhook-Secret",
        key   = "cfg_webhook_secret",
    )

    _, col_wb_test = st.columns([3, 1])
    with col_wb_test:
        if st.button("📡 測試 Webhook", use_container_width=True, key="test_webhook"):
            with st.spinner("測試中..."):
                ok, msg = test_webhook(new_webhook_url, new_webhook_secret)
            st.success(msg) if ok else st.error(msg)

    if not new_webhook_url:
        st.info("ℹ️ Webhook URL 未設定，觸發事件只會記錄到 DB")

    st.divider()

    # =====================================================
    # 區塊四：LINE 通知設定
    # =====================================================
    st.subheader("💬 LINE 通知設定")
    st.caption("AQI 超標時透過 LINE Messaging API 推播通知")

    new_line_token = st.text_input(
        "Channel Access Token",
        value = current["line_channel_token"],
        type  = "password",
        help  = "LINE Developers Console 取得的 Channel Access Token",
        key   = "cfg_line_token",
    )
    new_line_target = st.text_input(
        "推播目標 ID",
        value       = current["line_target_id"],
        placeholder = "userId 或 groupId",
        help        = "個人用戶填 userId（U開頭），群組填 groupId（C開頭）",
        key         = "cfg_line_target",
    )

    _, col_ln_test = st.columns([3, 1])
    with col_ln_test:
        if st.button("💬 測試 LINE", use_container_width=True, key="test_line"):
            with st.spinner("發送中..."):
                ok, msg = test_line(new_line_token, new_line_target)
            st.success(msg) if ok else st.error(msg)

    if not new_line_token:
        st.info("ℹ️ LINE Token 未設定，觸發時不會發送 LINE 通知")

    st.divider()

    # =====================================================
    # 區塊五：Email 設定
    # =====================================================
    st.subheader("📧 Email 設定")
    st.caption("月報產生後寄送給訂閱者，或觸發時發送警報 Email")

    col_e1, col_e2 = st.columns([3, 1])
    with col_e1:
        new_smtp_host = st.text_input(
            "SMTP 主機",
            value       = current["email_smtp_host"],
            placeholder = "smtp.gmail.com",
            key         = "cfg_smtp_host",
        )
    with col_e2:
        new_smtp_port = st.number_input(
            "SMTP 埠",
            min_value = 1,
            max_value = 65535,
            value     = int(current["email_smtp_port"]),
            key       = "cfg_smtp_port",
        )

    col_e3, col_e4 = st.columns(2)
    with col_e3:
        new_email_account = st.text_input(
            "寄件帳號",
            value       = current["email_account"],
            placeholder = "your@gmail.com",
            key         = "cfg_email_account",
        )
    with col_e4:
        new_email_password = st.text_input(
            "寄件密碼 / App Password",
            value = current["email_password"],
            type  = "password",
            help  = "Gmail 建議使用應用程式密碼（App Password）",
            key   = "cfg_email_password",
        )

    new_email_recipients = st.text_input(
        "預設收件人（逗號分隔）",
        value       = current["email_recipients"],
        placeholder = "user1@example.com, user2@example.com",
        help        = "月報寄送的預設收件人清單",
        key         = "cfg_email_recipients",
    )

    _, col_em_test = st.columns([3, 1])
    with col_em_test:
        if st.button("📧 測試 Email", use_container_width=True, key="test_email"):
            with st.spinner("發送測試信..."):
                ok, msg = test_email(
                    new_smtp_host, new_smtp_port,
                    new_email_account, new_email_password,
                    new_email_recipients,
                )
            st.success(msg) if ok else st.error(msg)

    if not new_email_account:
        st.info("ℹ️ Email 未設定，月報只能手動下載，無法自動寄送")

    st.divider()

    # =====================================================
    # 儲存 / 重設按鈕
    # =====================================================
    col_save, col_reset, _ = st.columns([2, 2, 4])
    with col_save:
        if st.button("💾 儲存所有設定", use_container_width=True, type="primary"):
            saves = [
                ("waqi_token",           new_token),
                ("scheduler_interval",   str(new_interval)),
                ("alert_cooldown_hours", str(new_cooldown)),
                ("webhook_url",          new_webhook_url),
                ("webhook_secret",       new_webhook_secret),
                ("line_channel_token",   new_line_token),
                ("line_target_id",       new_line_target),
                ("email_smtp_host",      new_smtp_host),
                ("email_smtp_port",      str(new_smtp_port)),
                ("email_account",        new_email_account),
                ("email_password",       new_email_password),
                ("email_recipients",     new_email_recipients),
            ]
            all_ok = all(save_setting(k, v) for k, v in saves)
            if all_ok:
                apply_settings({
                    "waqi_token":           new_token,
                    "scheduler_interval":   str(new_interval),
                    "alert_cooldown_hours": str(new_cooldown),
                })
                st.success("✅ 所有設定已儲存並套用")
            else:
                st.error("部分設定儲存失敗，請檢查 log")

    with col_reset:
        if st.button("↩️ 重設為預設值", use_container_width=True):
            for k, v in SETTING_KEYS.items():
                save_setting(k, v["default"])
            st.warning("已重設為預設值，請重新整理頁面")
            st.rerun()

    st.divider()

    # =====================================================
    # 診斷：目前設定狀態
    # =====================================================
    with st.expander("🔍 目前設定狀態（診斷用）"):
        conn = get_conn()
        rows = conn.execute(
            "SELECT key, value, updated_at FROM settings ORDER BY key"
        ).fetchall()
        conn.close()

        if rows:
            for row in rows:
                val = row["value"]
                if any(x in row["key"] for x in ("token", "secret", "password")):
                    val = val[:6] + "****" if len(val) > 6 else "****"
                st.text(f"  {row['key']:<25} = {val:<30} (更新：{row['updated_at'] or 'N/A'})")
        else:
            st.info("尚未儲存任何設定")
