"""
core/notify_email.py - Email 通知模組
功能：AQI 超標警報 Email、月報寄送
使用 SMTP，支援 Gmail App Password
"""

import smtplib
import io
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication


# ===== 1. 取得 Email 設定 =====

def _get_email_settings() -> dict:
    """從 settings 表讀取 Email 設定"""
    try:
        from core.db_init import get_conn
        conn = get_conn()
        rows = conn.execute("""
            SELECT key, value FROM settings
            WHERE key IN (
                'email_smtp_host', 'email_smtp_port',
                'email_account', 'email_password', 'email_recipients'
            )
        """).fetchall()
        conn.close()
        return {r["key"]: r["value"] for r in rows}
    except Exception:
        return {}


def _is_email_configured(settings: dict) -> bool:
    """確認 Email 設定是否完整"""
    return all([
        settings.get("email_account", "").strip(),
        settings.get("email_password", "").strip(),
        settings.get("email_recipients", "").strip(),
        settings.get("email_smtp_host", "").strip(),
    ])


def _get_recipients(settings: dict) -> list:
    """解析收件人清單"""
    raw = settings.get("email_recipients", "")
    return [r.strip() for r in raw.split(",") if r.strip()]


# ===== 2. 建立 SMTP 連線 =====

def _connect_smtp(settings: dict):
    """建立並回傳 SMTP 連線"""
    host = settings.get("email_smtp_host", "smtp.gmail.com")
    port = int(settings.get("email_smtp_port", 587))
    acc  = settings.get("email_account", "")
    pwd  = settings.get("email_password", "")

    server = smtplib.SMTP(host, port, timeout=15)
    server.ehlo()
    server.starttls()
    server.login(acc, pwd)
    return server


# ===== 3. AQI 等級文字 =====

def _aqi_label(aqi_val) -> tuple:
    """回傳 (等級文字, HTML 顏色)"""
    try:
        v = float(aqi_val)
    except (TypeError, ValueError):
        return "未知", "#999999"
    if v <= 50:   return "優良",          "#00E400"
    if v <= 100:  return "普通",          "#FFD700"
    if v <= 150:  return "敏感族群不健康", "#FF7E00"
    if v <= 200:  return "不健康",        "#FF0000"
    if v <= 300:  return "非常不健康",    "#8F3F97"
    return             "危險",           "#7E0023"


# ===== 4. 發送 AQI 警報 Email =====

def send_aqi_alert(city_name: str, city_key: str,
                   aqi: float, threshold: int) -> tuple:
    """
    發送 AQI 超標警報 Email。

    Args:
        city_name:  城市顯示名稱
        city_key:   WAQI 識別碼
        aqi:        當前 AQI 值
        threshold:  警戒閾值
    Returns:
        (bool, str)：(是否成功, 訊息)
    """
    settings = _get_email_settings()

    if not _is_email_configured(settings):
        return False, "email_not_configured"

    recipients = _get_recipients(settings)
    now_str    = datetime.now().strftime("%Y-%m-%d %H:%M")
    lv_text, lv_color = _aqi_label(aqi)
    over       = int(aqi) - threshold

    # ---- HTML 信件內容 ----
    html = f"""
    <html><body style="font-family:Arial,sans-serif;margin:0;padding:0;background:#f5f5f5;">
    <div style="max-width:600px;margin:20px auto;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">

      <!-- 標題列 -->
      <div style="background:#1F4E79;padding:20px;text-align:center;">
        <h1 style="color:white;margin:0;font-size:22px;">🚨 AQI 空氣品質警報</h1>
        <p style="color:#D6E4F0;margin:6px 0 0;">AQI Monitor</p>
      </div>

      <!-- AQI 大數字 -->
      <div style="text-align:center;padding:30px 20px;background:{lv_color}15;border-bottom:4px solid {lv_color};">
        <div style="font-size:72px;font-weight:bold;color:{lv_color};line-height:1;">{int(aqi)}</div>
        <div style="font-size:18px;color:{lv_color};margin-top:8px;">{lv_text}</div>
        <div style="font-size:13px;color:#666;margin-top:4px;">超閾值 +{over}</div>
      </div>

      <!-- 詳細資訊 -->
      <div style="padding:24px;">
        <table style="width:100%;border-collapse:collapse;">
          <tr style="border-bottom:1px solid #eee;">
            <td style="padding:10px 0;color:#666;width:40%;">📍 監控城市</td>
            <td style="padding:10px 0;font-weight:bold;">{city_name}</td>
          </tr>
          <tr style="border-bottom:1px solid #eee;">
            <td style="padding:10px 0;color:#666;">⚠️ 警戒閾值</td>
            <td style="padding:10px 0;">{threshold}</td>
          </tr>
          <tr style="border-bottom:1px solid #eee;">
            <td style="padding:10px 0;color:#666;">🕐 觸發時間</td>
            <td style="padding:10px 0;">{now_str}</td>
          </tr>
          <tr>
            <td style="padding:10px 0;color:#666;">🔑 站台識別碼</td>
            <td style="padding:10px 0;font-size:12px;color:#999;">{city_key}</td>
          </tr>
        </table>

        <div style="margin-top:20px;padding:16px;background:#FFF8E7;border-left:4px solid #FFC107;border-radius:4px;">
          <p style="margin:0;color:#5D4037;font-size:14px;">
            ⚠️ 建議減少戶外活動，外出請配戴口罩，關閉門窗並開啟空氣清淨機。
          </p>
        </div>
      </div>

      <!-- 頁腳 -->
      <div style="background:#f8f9fa;padding:16px;text-align:center;font-size:12px;color:#999;">
        此信件由 AQI Monitor 自動發送 · {now_str}<br>
        資料來源：World Air Quality Index（WAQI）
      </div>
    </div>
    </body></html>
    """

    # ---- 純文字備用 ----
    text = (
        f"AQI 空氣品質警報\n\n"
        f"城市：{city_name}\n"
        f"AQI：{int(aqi)}（{lv_text}，超閾值 +{over}）\n"
        f"閾值：{threshold}\n"
        f"時間：{now_str}\n\n"
        f"建議減少戶外活動，外出請配戴口罩。"
    )

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🚨 AQI 警報：{city_name} AQI={int(aqi)}（{lv_text}）"
        msg["From"]    = settings["email_account"]
        msg["To"]      = ", ".join(recipients)
        msg.attach(MIMEText(text, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html",  "utf-8"))

        server = _connect_smtp(settings)
        server.sendmail(settings["email_account"], recipients, msg.as_string())
        server.quit()
        return True, f"email_sent（{len(recipients)} 位收件人）"

    except Exception as e:
        return False, f"Email 發送失敗：{e}"


# ===== 5. 發送月報 Email（含附件）=====

def send_report_email(city_names: list, year: int, month: int,
                      excel_bytes: bytes = None,
                      pdf_bytes:   bytes = None,
                      ppt_bytes:   bytes = None,
                      recipients:  list  = None) -> tuple:
    """
    發送月報 Email，可附帶 Excel / PDF / PPT 附件。

    Args:
        city_names:  城市名稱清單
        year:        報告年份
        month:       報告月份
        excel_bytes: Excel 檔案內容（bytes），None 表示不附加
        pdf_bytes:   PDF 檔案內容（bytes），None 表示不附加
        ppt_bytes:   PPT 檔案內容（bytes），None 表示不附加
        recipients:  收件人清單，None 則使用系統設定的預設收件人
    Returns:
        (bool, str)
    """
    settings = _get_email_settings()

    if not _is_email_configured(settings):
        return False, "email_not_configured"

    # 收件人：優先使用傳入的，其次用系統設定
    if not recipients:
        recipients = _get_recipients(settings)
    if not recipients:
        return False, "無收件人"

    now_str    = datetime.now().strftime("%Y-%m-%d %H:%M")
    city_str   = "、".join(city_names)
    fname_base = f"AQI月報_{year}{month:02d}_{'_'.join(city_names[:2])}"

    # ---- HTML 信件內容 ----
    html = f"""
    <html><body style="font-family:Arial,sans-serif;margin:0;padding:0;background:#f5f5f5;">
    <div style="max-width:600px;margin:20px auto;background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.1);">

      <!-- 標題列 -->
      <div style="background:#1F4E79;padding:20px;text-align:center;">
        <h1 style="color:white;margin:0;font-size:22px;">📊 空氣品質月報</h1>
        <p style="color:#D6E4F0;margin:6px 0 0;">{year} 年 {month:02d} 月</p>
      </div>

      <!-- 報告資訊 -->
      <div style="padding:24px;">
        <table style="width:100%;border-collapse:collapse;">
          <tr style="border-bottom:1px solid #eee;">
            <td style="padding:10px 0;color:#666;width:40%;">📅 報告期間</td>
            <td style="padding:10px 0;font-weight:bold;">{year} 年 {month:02d} 月</td>
          </tr>
          <tr style="border-bottom:1px solid #eee;">
            <td style="padding:10px 0;color:#666;">📍 監控城市</td>
            <td style="padding:10px 0;">{city_str}</td>
          </tr>
          <tr style="border-bottom:1px solid #eee;">
            <td style="padding:10px 0;color:#666;">📎 附件格式</td>
            <td style="padding:10px 0;">
              {'📗 Excel ' if excel_bytes else ''}
              {'📕 PDF '   if pdf_bytes   else ''}
              {'📘 PPT '   if ppt_bytes   else ''}
            </td>
          </tr>
          <tr>
            <td style="padding:10px 0;color:#666;">🕐 發送時間</td>
            <td style="padding:10px 0;">{now_str}</td>
          </tr>
        </table>

        <div style="margin-top:20px;padding:16px;background:#E8F4FD;border-left:4px solid #2E75B6;border-radius:4px;">
          <p style="margin:0;color:#1F4E79;font-size:14px;">
            本報告由 AQI Monitor 自動產生，資料來源為 WAQI 免費 API，每 30 分鐘更新一次。
          </p>
        </div>
      </div>

      <!-- 頁腳 -->
      <div style="background:#f8f9fa;padding:16px;text-align:center;font-size:12px;color:#999;">
        俞威名（WeiMing Yu）· {now_str}
      </div>
    </div>
    </body></html>
    """

    text = (
        f"空氣品質月報 {year}/{month:02d}\n\n"
        f"監控城市：{city_str}\n"
        f"發送時間：{now_str}\n\n"
        f"請查看附件中的報告檔案。\n\n"
        f"俞威名（WeiMing Yu）"
    )

    try:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = f"📊 空氣品質月報 {year}/{month:02d} — {city_str}"
        msg["From"]    = settings["email_account"]
        msg["To"]      = ", ".join(recipients)

        # 信件本文
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(text, "plain", "utf-8"))
        alt.attach(MIMEText(html, "html",  "utf-8"))
        msg.attach(alt)

        # ---- 附件 ----
        if excel_bytes:
            part = MIMEApplication(excel_bytes, Name=f"{fname_base}.xlsx")
            part["Content-Disposition"] = f'attachment; filename="{fname_base}.xlsx"'
            msg.attach(part)

        if pdf_bytes:
            part = MIMEApplication(pdf_bytes, Name=f"{fname_base}.pdf")
            part["Content-Disposition"] = f'attachment; filename="{fname_base}.pdf"'
            msg.attach(part)

        if ppt_bytes:
            part = MIMEApplication(ppt_bytes, Name=f"{fname_base}.pptx")
            part["Content-Disposition"] = f'attachment; filename="{fname_base}.pptx"'
            msg.attach(part)

        server = _connect_smtp(settings)
        server.sendmail(settings["email_account"], recipients, msg.as_string())
        server.quit()
        return True, f"月報已寄送（{len(recipients)} 位收件人）"

    except Exception as e:
        return False, f"Email 發送失敗：{e}"
