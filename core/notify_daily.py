"""
core/notify_daily.py - 每日摘要 Email 產生與發送模組
功能：依訂閱會員設定，產生個人化每日/週報/月報摘要並寄送
"""

import json
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import pandas as pd

from core.db_init import get_conn


# ===== 1. AQI 工具函式 =====

def _aqi_label(aqi) -> tuple:
    """回傳 (等級文字, HTML 顏色, emoji)"""
    try:
        v = float(aqi)
    except (TypeError, ValueError):
        return "未知", "#999999", "❓"
    if v <= 50:   return "優良",           "#00C400", "🟢"
    if v <= 100:  return "普通",           "#DAA000", "🟡"
    if v <= 150:  return "敏感族群不健康", "#FF7E00", "🟠"
    if v <= 200:  return "不健康",         "#E00000", "🔴"
    if v <= 300:  return "非常不健康",     "#8F3F97", "🟣"
    return             "危險",            "#7E0023", "⚫"


def _activity_advice(max_aqi) -> str:
    """依最高 AQI 給出活動建議"""
    try:
        v = float(max_aqi)
    except (TypeError, ValueError):
        return "無法判斷，請參考當地環保機關公告。"
    if v <= 50:
        return "✅ 空氣品質優良，適合戶外活動，盡情享受新鮮空氣！"
    if v <= 100:
        return "🟡 一般民眾可正常活動，敏感族群建議減少激烈戶外運動。"
    if v <= 150:
        return "🟠 敏感族群（氣喘、心肺疾病）避免戶外活動，一般民眾減少長時間戶外停留。"
    if v <= 200:
        return "🔴 建議所有人減少戶外活動，外出請配戴口罩，開啟室內空氣清淨機。"
    return "⚫ 空氣品質危險，避免一切戶外活動，緊閉門窗，開啟空氣清淨機強效模式。"


# ===== 2. 查詢資料 =====

def _query_today_data(city_keys: list) -> pd.DataFrame:
    """查詢今日各城市歷史資料"""
    if not city_keys:
        return pd.DataFrame()

    today = datetime.now().strftime("%Y-%m-%d")
    placeholders = ",".join(["?"] * len(city_keys))

    conn = get_conn()
    df   = pd.read_sql_query(f"""
        SELECT h.city_key, w.display_name,
               h.aqi, h.pm25, h.pm10, h.o3, h.no2,
               h.temp, h.humidity, h.fetch_time
        FROM   aqi_history h
        JOIN   watch_list   w ON h.city_key = w.city_key
        WHERE  h.city_key IN ({placeholders})
          AND  DATE(h.fetch_time) = ?
        ORDER  BY h.city_key, h.fetch_time
    """, conn, params=city_keys + [today])
    conn.close()
    return df


def _query_yesterday_data(city_keys: list) -> pd.DataFrame:
    """查詢昨日各城市歷史資料（供趨勢比較）"""
    if not city_keys:
        return pd.DataFrame()

    yesterday    = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    placeholders = ",".join(["?"] * len(city_keys))

    conn = get_conn()
    df   = pd.read_sql_query(f"""
        SELECT h.city_key, w.display_name, AVG(h.aqi) as avg_aqi
        FROM   aqi_history h
        JOIN   watch_list   w ON h.city_key = w.city_key
        WHERE  h.city_key IN ({placeholders})
          AND  DATE(h.fetch_time) = ?
        GROUP  BY h.city_key
    """, conn, params=city_keys + [yesterday])
    conn.close()
    return df


def _query_week_avg(city_keys: list) -> pd.DataFrame:
    """查詢近 7 天各城市平均 AQI"""
    if not city_keys:
        return pd.DataFrame()

    week_ago     = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    placeholders = ",".join(["?"] * len(city_keys))

    conn = get_conn()
    df   = pd.read_sql_query(f"""
        SELECT h.city_key, AVG(h.aqi) as week_avg
        FROM   aqi_history h
        WHERE  h.city_key IN ({placeholders})
          AND  DATE(h.fetch_time) >= ?
        GROUP  BY h.city_key
    """, conn, params=city_keys + [week_ago])
    conn.close()
    return df


def _query_forecast(city_keys: list) -> dict:
    """查詢明日預報資料"""
    if not city_keys:
        return {}

    tomorrow     = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    placeholders = ",".join(["?"] * len(city_keys))

    conn = get_conn()
    rows = conn.execute(f"""
        SELECT city_key, pollutant, avg_val, max_val, min_val
        FROM   aqi_forecast
        WHERE  city_key     IN ({placeholders})
          AND  forecast_day  = ?
          AND  pollutant     = 'pm25'
        ORDER  BY city_key
    """, city_keys + [tomorrow]).fetchall()
    conn.close()

    return {r["city_key"]: dict(r) for r in rows}


# ===== 3. 產生 HTML Email 內容 =====

def build_daily_html(city_keys: list, city_names_map: dict,
                     report_date: str = None) -> str:
    """
    產生每日摘要 HTML Email 內容。

    Args:
        city_keys:      訂閱城市 key 清單
        city_names_map: {city_key: display_name}
        report_date:    報告日期字串（預設今天）
    Returns:
        HTML 字串
    """
    today     = report_date or datetime.now().strftime("%Y-%m-%d")
    today_str = datetime.now().strftime("%Y 年 %m 月 %d 日")

    # ---- 查詢資料 ----
    df        = _query_today_data(city_keys)
    df_yday   = _query_yesterday_data(city_keys)
    df_week   = _query_week_avg(city_keys)
    forecasts = _query_forecast(city_keys)

    # ---- 若無資料 ----
    if df.empty:
        return f"""
        <html><body style="font-family:Arial,sans-serif;padding:20px;">
        <h2>空氣品質每日摘要 — {today_str}</h2>
        <p>今日尚無資料，請確認排程正常執行。</p>
        </body></html>
        """

    # ---- 今日各城市統計 ----
    city_stats = df.groupby(["city_key", "display_name"]).agg(
        avg_aqi  = ("aqi",      "mean"),
        max_aqi  = ("aqi",      "max"),
        min_aqi  = ("aqi",      "min"),
        avg_pm25 = ("pm25",     "mean"),
        avg_pm10 = ("pm10",     "mean"),
        avg_o3   = ("o3",       "mean"),
        avg_no2  = ("no2",      "mean"),
        count    = ("aqi",      "count"),
    ).reset_index()

    # ---- 昨日 / 週均對照 ----
    yday_map = {}
    if not df_yday.empty:
        yday_map = dict(zip(df_yday["city_key"], df_yday["avg_aqi"]))

    week_map = {}
    if not df_week.empty:
        week_map = dict(zip(df_week["city_key"], df_week["week_avg"]))

    # ---- 最高/最低城市 ----
    valid = city_stats.dropna(subset=["avg_aqi"])
    max_row = valid.loc[valid["avg_aqi"].idxmax()] if len(valid) else None
    min_row = valid.loc[valid["avg_aqi"].idxmin()] if len(valid) else None
    overall_max = valid["max_aqi"].max() if len(valid) else None

    # ---- 超標城市 ----
    exceed = city_stats[city_stats["avg_aqi"] > 100] if len(city_stats) else pd.DataFrame()

    # ===== 開始組 HTML =====
    html_parts = [f"""
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="font-family:'Microsoft JhengHei',Arial,sans-serif;
                 margin:0;padding:0;background:#f5f5f5;">
    <div style="max-width:650px;margin:20px auto;background:#fff;
                border-radius:10px;overflow:hidden;
                box-shadow:0 2px 12px rgba(0,0,0,0.1);">

      <!-- 標題列 -->
      <div style="background:#1F4E79;padding:24px;text-align:center;">
        <h1 style="color:#fff;margin:0;font-size:22px;">🌬️ 空氣品質每日摘要</h1>
        <p style="color:#D6E4F0;margin:8px 0 0;font-size:14px;">{today_str}</p>
      </div>
    """]

    # ===== 區塊一：今日各城市 AQI =====
    html_parts.append("""
      <div style="padding:20px 24px 8px;">
        <h2 style="color:#1F4E79;font-size:16px;border-bottom:2px solid #D6E4F0;
                   padding-bottom:8px;margin-bottom:16px;">
          📍 今日各城市 AQI 概況
        </h2>
    """)

    for _, row in city_stats.iterrows():
        lv, color, emoji = _aqi_label(row["avg_aqi"])
        ck   = row["city_key"]
        name = row["display_name"]

        # 趨勢箭頭
        trend = ""
        if ck in yday_map and pd.notna(yday_map[ck]):
            diff = row["avg_aqi"] - yday_map[ck]
            if diff > 5:
                trend = f"<span style='color:#E00000'>▲ {diff:.1f}</span>"
            elif diff < -5:
                trend = f"<span style='color:#00C400'>▼ {abs(diff):.1f}</span>"
            else:
                trend = f"<span style='color:#999'>— {diff:+.1f}</span>"

        html_parts.append(f"""
        <div style="display:flex;align-items:center;padding:10px 12px;
                    margin-bottom:8px;border-radius:8px;
                    background:{color}15;border-left:4px solid {color};">
          <div style="flex:1;">
            <span style="font-weight:bold;color:#1F4E79;">{name}</span>
          </div>
          <div style="text-align:center;width:80px;">
            <span style="font-size:28px;font-weight:900;color:{color};">
              {row['avg_aqi']:.0f}
            </span>
          </div>
          <div style="text-align:right;width:120px;">
            <span style="font-size:12px;color:{color};">{emoji} {lv}</span><br>
            <span style="font-size:11px;color:#888;">{trend}</span>
          </div>
        </div>
        """)

    html_parts.append("</div>")

    # ===== 區塊二：今日最高/最低 =====
    if max_row is not None and min_row is not None:
        max_lv, max_color, max_emoji = _aqi_label(max_row["avg_aqi"])
        min_lv, min_color, min_emoji = _aqi_label(min_row["avg_aqi"])
        html_parts.append(f"""
      <div style="padding:8px 24px 8px;">
        <div style="display:flex;gap:12px;">
          <div style="flex:1;background:#FFF3F3;border-radius:8px;padding:12px;
                      border-top:3px solid {max_color};">
            <div style="font-size:11px;color:#888;">今日最高</div>
            <div style="font-weight:bold;color:#1F4E79;">{max_row['display_name']}</div>
            <div style="font-size:24px;font-weight:900;color:{max_color};">
              {max_row['avg_aqi']:.0f}
            </div>
            <div style="font-size:12px;color:{max_color};">{max_emoji} {max_lv}</div>
          </div>
          <div style="flex:1;background:#F3FFF3;border-radius:8px;padding:12px;
                      border-top:3px solid {min_color};">
            <div style="font-size:11px;color:#888;">今日最低</div>
            <div style="font-weight:bold;color:#1F4E79;">{min_row['display_name']}</div>
            <div style="font-size:24px;font-weight:900;color:{min_color};">
              {min_row['avg_aqi']:.0f}
            </div>
            <div style="font-size:12px;color:{min_color};">{min_emoji} {min_lv}</div>
          </div>
        </div>
      </div>
        """)

    # ===== 區塊三：污染物摘要 =====
    overall = city_stats.mean(numeric_only=True)
    html_parts.append(f"""
      <div style="padding:16px 24px 8px;">
        <h2 style="color:#1F4E79;font-size:16px;border-bottom:2px solid #D6E4F0;
                   padding-bottom:8px;margin-bottom:12px;">
          🔬 污染物摘要（各城市今日平均）
        </h2>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          {"".join([
            f'''<div style="flex:1;min-width:100px;text-align:center;
                            background:#F0F4F8;border-radius:8px;padding:10px;">
                  <div style="font-size:11px;color:#888;">{label}</div>
                  <div style="font-size:20px;font-weight:bold;color:#1F4E79;">{val:.1f}</div>
                  <div style="font-size:10px;color:#aaa;">{unit}</div>
                </div>'''
            for label, col, unit in [
                ("PM2.5", "avg_pm25", "μg/m³"),
                ("PM10",  "avg_pm10", "μg/m³"),
                ("O₃",    "avg_o3",   "ppb"),
                ("NO₂",   "avg_no2",  "ppb"),
            ]
            if pd.notna(overall.get(col)) and (val := overall.get(col, 0))
          ])}
        </div>
      </div>
    """)

    # ===== 區塊四：超標警示 =====
    if len(exceed) > 0:
        html_parts.append("""
      <div style="padding:16px 24px 8px;">
        <div style="background:#FFF0F0;border-left:4px solid #E00000;
                    border-radius:8px;padding:14px;">
          <h3 style="color:#E00000;margin:0 0 8px;font-size:14px;">
            ⚠️ 今日超標城市（AQI > 100）
          </h3>
        """)
        for _, row in exceed.iterrows():
            lv, color, emoji = _aqi_label(row["avg_aqi"])
            html_parts.append(f"""
          <div style="margin-bottom:6px;">
            <span style="font-weight:bold;">{row['display_name']}</span>：
            <span style="color:{color};font-weight:bold;">{row['avg_aqi']:.0f}</span>
            <span style="font-size:12px;color:{color};"> {emoji} {lv}</span>
          </div>
            """)
        html_parts.append("</div></div>")
    else:
        html_parts.append("""
      <div style="padding:8px 24px;">
        <div style="background:#F0FFF0;border-left:4px solid #00C400;
                    border-radius:8px;padding:12px;">
          ✅ 今日所有城市 AQI 均在 100 以下，空氣品質良好！
        </div>
      </div>
        """)

    # ===== 區塊五：活動建議 =====
    advice = _activity_advice(overall_max)
    html_parts.append(f"""
      <div style="padding:16px 24px 8px;">
        <h2 style="color:#1F4E79;font-size:16px;border-bottom:2px solid #D6E4F0;
                   padding-bottom:8px;margin-bottom:12px;">
          💡 今日活動建議
        </h2>
        <div style="background:#EBF3FA;border-radius:8px;padding:14px;
                    font-size:14px;color:#1F4E79;line-height:1.6;">
          {advice}
        </div>
      </div>
    """)

    # ===== 區塊六：明日預報 =====
    if forecasts:
        html_parts.append("""
      <div style="padding:16px 24px 8px;">
        <h2 style="color:#1F4E79;font-size:16px;border-bottom:2px solid #D6E4F0;
                   padding-bottom:8px;margin-bottom:12px;">
          📅 明日 PM2.5 預報
        </h2>
        """)
        tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%m/%d")
        for ck in city_keys:
            if ck in forecasts:
                fc   = forecasts[ck]
                name = city_names_map.get(ck, ck)
                lv, color, emoji = _aqi_label(fc.get("avg_val"))
                html_parts.append(f"""
        <div style="display:flex;align-items:center;margin-bottom:8px;
                    padding:8px 12px;background:#F8F9FA;border-radius:6px;">
          <span style="flex:1;font-size:13px;">{name}</span>
          <span style="font-size:13px;font-weight:bold;color:{color};">
            PM2.5 均值：{fc.get('avg_val', 'N/A'):.1f}
          </span>
          <span style="font-size:12px;color:#888;margin-left:8px;">
            ({fc.get('min_val', 'N/A'):.0f}~{fc.get('max_val', 'N/A'):.0f})
          </span>
        </div>
                """)
        html_parts.append("</div>")

    # ===== 區塊七：本週趨勢比較 =====
    if week_map:
        html_parts.append("""
      <div style="padding:16px 24px 8px;">
        <h2 style="color:#1F4E79;font-size:16px;border-bottom:2px solid #D6E4F0;
                   padding-bottom:8px;margin-bottom:12px;">
          📈 本週趨勢比較
        </h2>
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
          <tr style="background:#1F4E79;color:#fff;">
            <th style="padding:8px;text-align:left;">城市</th>
            <th style="padding:8px;text-align:center;">今日均值</th>
            <th style="padding:8px;text-align:center;">昨日均值</th>
            <th style="padding:8px;text-align:center;">7日均值</th>
            <th style="padding:8px;text-align:center;">趨勢</th>
          </tr>
        """)
        for i, row in enumerate(city_stats.itertuples()):
            ck     = row.city_key
            today_v = row.avg_aqi
            yday_v  = yday_map.get(ck)
            week_v  = week_map.get(ck)
            bg      = "#F4F8FC" if i % 2 == 0 else "#FFFFFF"

            # 趨勢判斷
            if yday_v and pd.notna(yday_v):
                diff = today_v - yday_v
                trend_html = (
                    f"<span style='color:#E00000'>↑ 上升</span>" if diff > 5 else
                    f"<span style='color:#00C400'>↓ 下降</span>" if diff < -5 else
                    f"<span style='color:#888'>→ 持平</span>"
                )
            else:
                trend_html = "<span style='color:#ccc'>—</span>"

            html_parts.append(f"""
          <tr style="background:{bg};">
            <td style="padding:8px;">{row.display_name}</td>
            <td style="padding:8px;text-align:center;font-weight:bold;">
              {today_v:.1f}
            </td>
            <td style="padding:8px;text-align:center;color:#888;">
              {f'{yday_v:.1f}' if yday_v and pd.notna(yday_v) else 'N/A'}
            </td>
            <td style="padding:8px;text-align:center;color:#888;">
              {f'{week_v:.1f}' if week_v and pd.notna(week_v) else 'N/A'}
            </td>
            <td style="padding:8px;text-align:center;">{trend_html}</td>
          </tr>
            """)
        html_parts.append("</table></div>")

    # ===== 頁腳 =====
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    html_parts.append(f"""
      <!-- 頁腳 -->
      <div style="background:#F8F9FA;padding:16px 24px;margin-top:16px;
                  text-align:center;font-size:11px;color:#999;">
        此郵件由 AQI Monitor 自動發送 · {now_str}<br>
        資料來源：World Air Quality Index（WAQI）· 每 30 分鐘更新<br>
        如需取消訂閱，請聯繫系統管理員。
      </div>
    </div>
    </body></html>
    """)

    return "".join(html_parts)


# ===== 4. 發送每日摘要給單一會員 =====

def send_daily_to_subscriber(subscriber: dict) -> tuple:
    """
    產生並發送每日摘要 Email 給指定會員。

    Args:
        subscriber: subscribers 資料表的一筆記錄（dict）
    Returns:
        (bool, str)：(是否成功, 訊息)
    """
    from core.notify_email import _get_email_settings, _connect_smtp

    settings = _get_email_settings()
    if not settings.get("email_account") or not settings.get("email_password"):
        return False, "email_not_configured"

    city_keys = json.loads(subscriber.get("cities", "[]"))
    if not city_keys:
        return False, "no_cities"

    # 取得城市名稱對照表
    conn = get_conn()
    rows = conn.execute(
        f"SELECT city_key, display_name FROM watch_list WHERE city_key IN ({','.join(['?']*len(city_keys))})",
        city_keys
    ).fetchall()
    conn.close()
    city_names_map = {r["city_key"]: r["display_name"] for r in rows}

    today_str = datetime.now().strftime("%Y 年 %m 月 %d 日")

    try:
        html = build_daily_html(city_keys, city_names_map)
        text = f"空氣品質每日摘要 — {today_str}\n\n請以 HTML 格式查看此郵件。"

        msg            = MIMEMultipart("alternative")
        msg["Subject"] = f"🌬️ 空氣品質每日摘要 — {today_str}"
        msg["From"]    = settings["email_account"]
        msg["To"]      = subscriber["email"]
        msg.attach(MIMEText(text, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html",  "utf-8"))

        server = _connect_smtp(settings)
        server.sendmail(settings["email_account"], [subscriber["email"]], msg.as_string())
        server.quit()
        return True, "sent"

    except Exception as e:
        return False, str(e)


# ===== 5. 批次發送（由排程呼叫）=====

def send_scheduled_reports():
    """
    檢查所有啟用中的訂閱會員，依方案和時間決定是否發送。
    由 APScheduler 每小時整點呼叫一次。
    """
    now      = datetime.now()
    cur_hour = now.hour
    weekday  = now.weekday()   # 0=週一 6=週日
    day      = now.day

    conn = get_conn()
    subs = conn.execute(
        "SELECT * FROM subscribers WHERE is_active = 1"
    ).fetchall()
    conn.close()

    if not subs:
        return

    print(f"  📧 檢查訂閱發送：{len(subs)} 位會員，目前 {cur_hour:02d}:00")

    for sub in subs:
        sub_dict  = dict(sub)
        plan      = sub_dict["plan"]
        send_hour = sub_dict["send_hour"] or 8

        # ---- 時間不符，跳過 ----
        if cur_hour != send_hour:
            continue

        # ---- 依方案判斷是否發送 ----
        should_send = False
        if plan == "daily":
            should_send = True
        elif plan == "weekly":
            should_send = (weekday == (sub_dict["send_weekday"] or 0))
        elif plan == "monthly":
            should_send = (day == (sub_dict["send_day"] or 1))

        if not should_send:
            continue

        # ---- 發送並記錄 =====
        print(f"  📤 發送 {plan} 摘要給：{sub_dict['name']} ({sub_dict['email']})")
        ok, msg = send_daily_to_subscriber(sub_dict)

        # 寫入 subscription_log
        try:
            conn2 = get_conn()
            conn2.execute("""
                INSERT INTO subscription_log
                    (subscriber_id, plan, report_type, sent_at, status, message)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                sub_dict["id"], plan, "email",
                now.strftime("%Y-%m-%d %H:%M:%S"),
                "sent" if ok else "failed",
                msg,
            ))
            conn2.commit()
            conn2.close()
        except Exception as e:
            print(f"  ❌ subscription_log 寫入失敗：{e}")

        status = "✅" if ok else "❌"
        print(f"  {status} {sub_dict['name']}：{msg}")
