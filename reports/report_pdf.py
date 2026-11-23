"""
reports/report_pdf.py - PDF 月報產生模組
功能：從 aqi_history 撈資料，產生格式化的 PDF 月報（會員版）
使用 reportlab + 微軟正黑體，配合品牌色
"""

import io
import os
from datetime import datetime
import pandas as pd

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics import renderPDF

from core.db_init import get_conn


# ===== 1. 字型註冊 =====

def _register_fonts():
    """註冊微軟正黑體（Windows 環境）"""
    font_regular = r"C:\Windows\Fonts\msjh.ttc"
    font_bold    = r"C:\Windows\Fonts\msjhbd.ttc"
    try:
        pdfmetrics.registerFont(TTFont("NotoTC",      font_regular, subfontIndex=0))
        pdfmetrics.registerFont(TTFont("NotoTC-Bold", font_bold,    subfontIndex=0))
    except Exception:
        try:
            pdfmetrics.registerFont(TTFont("NotoTC",      font_regular, subfontIndex=0))
            pdfmetrics.registerFont(TTFont("NotoTC-Bold", font_regular, subfontIndex=0))
        except Exception:
            pass   # 字型不存在時使用系統預設


# ===== 2. 色彩定義 =====
NAVY    = colors.HexColor("#1F4E79")
BLUE    = colors.HexColor("#2E75B6")
ACCENT  = colors.HexColor("#2B5797")
LIGHT   = colors.HexColor("#D6E4F0")
GRAY    = colors.HexColor("#8A9BB0")
WHITE   = colors.white
BLACK   = colors.HexColor("#1F1F1F")

AQI_GOOD    = colors.HexColor("#00E400")
AQI_OK      = colors.HexColor("#FFFF00")
AQI_WARN    = colors.HexColor("#FF7E00")
AQI_BAD     = colors.HexColor("#FF0000")
AQI_VERYBAD = colors.HexColor("#8F3F97")
AQI_HAZARD  = colors.HexColor("#7E0023")


# ===== 3. 樣式定義 =====

def _get_styles():
    """建立所有段落樣式"""
    return {
        "title": ParagraphStyle(
            "title",
            fontName  = "NotoTC-Bold",
            fontSize  = 22,
            textColor = WHITE,
            alignment = 1,
            spaceAfter= 6,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            fontName  = "NotoTC",
            fontSize  = 13,
            textColor = WHITE,
            alignment = 1,
            spaceAfter= 4,
        ),
        "h1": ParagraphStyle(
            "h1",
            fontName   = "NotoTC-Bold",
            fontSize   = 14,
            textColor  = NAVY,
            spaceBefore= 14,
            spaceAfter = 6,
            borderPad  = 4,
        ),
        "h2": ParagraphStyle(
            "h2",
            fontName   = "NotoTC-Bold",
            fontSize   = 11,
            textColor  = BLUE,
            spaceBefore= 8,
            spaceAfter = 4,
        ),
        "body": ParagraphStyle(
            "body",
            fontName   = "NotoTC",
            fontSize   = 10,
            textColor  = BLACK,
            spaceAfter = 4,
            leading    = 16,
        ),
        "caption": ParagraphStyle(
            "caption",
            fontName   = "NotoTC",
            fontSize   = 8,
            textColor  = GRAY,
            spaceAfter = 2,
        ),
        "footer": ParagraphStyle(
            "footer",
            fontName  = "NotoTC",
            fontSize  = 8,
            textColor = GRAY,
            alignment = 1,
        ),
    }


# ===== 4. 工具函式 =====

def _aqi_color(aqi_val):
    """依 AQI 值回傳 reportlab 顏色"""
    try:
        v = float(aqi_val)
    except (TypeError, ValueError):
        return GRAY
    if v <= 50:   return AQI_GOOD
    if v <= 100:  return AQI_OK
    if v <= 150:  return AQI_WARN
    if v <= 200:  return AQI_BAD
    if v <= 300:  return AQI_VERYBAD
    return AQI_HAZARD

def _aqi_label(aqi_val):
    """依 AQI 值回傳等級文字"""
    try:
        v = float(aqi_val)
    except (TypeError, ValueError):
        return "無資料"
    if v <= 50:   return "優良"
    if v <= 100:  return "普通"
    if v <= 150:  return "敏感族群不健康"
    if v <= 200:  return "不健康"
    if v <= 300:  return "非常不健康"
    return "危險"

def _make_table(data, col_widths, header_bg=NAVY):
    """建立格式化表格"""
    t = Table(data, colWidths=col_widths)
    style = TableStyle([
        # 標題列
        ("BACKGROUND",  (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR",   (0, 0), (-1, 0), WHITE),
        ("FONTNAME",    (0, 0), (-1, 0), "NotoTC-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0), 9),
        ("ALIGN",       (0, 0), (-1, 0), "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING",(0, 0), (-1, 0), 6),
        # 資料列
        ("FONTNAME",    (0, 1), (-1, -1), "NotoTC"),
        ("FONTSIZE",    (0, 1), (-1, -1), 9),
        ("ALIGN",       (1, 1), (-1, -1), "CENTER"),
        ("ALIGN",       (0, 1), (0, -1), "LEFT"),
        ("TOPPADDING",  (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 1), (-1, -1), 4),
        # 格線
        ("GRID",        (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("LINEBELOW",   (0, 0), (-1, 0), 1.5, BLUE),
    ])
    # 奇偶列著色
    for i in range(1, len(data)):
        bg = LIGHT if i % 2 == 0 else WHITE
        style.add("BACKGROUND", (0, i), (-1, i), bg)
    t.setStyle(style)
    return t


# ===== 5. 查詢資料 =====

def _query_data(city_keys: list, year: int, month: int):
    """查詢月報所需資料"""
    placeholders = ",".join(["?"] * len(city_keys))
    month_str    = f"{year}-{month:02d}"

    conn = get_conn()
    df   = pd.read_sql_query(f"""
        SELECT h.city_key, w.display_name,
               h.fetch_time, h.aqi, h.pm25, h.pm10,
               h.no2, h.co, h.so2, h.o3, h.temp, h.humidity
        FROM   aqi_history h
        JOIN   watch_list   w ON h.city_key = w.city_key
        WHERE  h.city_key IN ({placeholders})
          AND  strftime('%Y-%m', h.fetch_time) = ?
        ORDER  BY h.city_key, h.fetch_time
    """, conn, params=city_keys + [month_str])

    alert_df = pd.read_sql_query(f"""
        SELECT city_key, display_name, aqi, threshold,
               webhook_status, triggered_at
        FROM   alert_log
        WHERE  city_key IN ({placeholders})
          AND  strftime('%Y-%m', triggered_at) = ?
        ORDER  BY triggered_at
    """, conn, params=city_keys + [month_str])
    conn.close()

    if not df.empty:
        df["fetch_time"] = pd.to_datetime(df["fetch_time"])
        df["date"]       = df["fetch_time"].dt.date

    return df, alert_df


# ===== 6. 頁首頁尾 =====

def _on_first_page(canvas, doc):
    """第一頁：封面頁首"""
    canvas.saveState()
    w, h = A4

    # 深藍背景區塊
    canvas.setFillColor(NAVY)
    canvas.rect(0, h - 9*cm, w, 9*cm, fill=1, stroke=0)

    # 標題
    canvas.setFillColor(WHITE)
    canvas.setFont("NotoTC-Bold", 26)
    canvas.drawCentredString(w/2, h - 3.5*cm, "空氣品質月報")
    canvas.setFont("NotoTC", 13)
    canvas.drawCentredString(w/2, h - 4.8*cm, "Air Quality Monthly Report")

    # 裝飾線
    canvas.setStrokeColor(colors.HexColor("#2E75B6"))
    canvas.setLineWidth(2)
    canvas.line(3*cm, h - 5.5*cm, w - 3*cm, h - 5.5*cm)

    canvas.restoreState()


def _on_later_pages(canvas, doc):
    """後續頁：頁首 + 頁碼"""
    canvas.saveState()
    w, h = A4

    # 頂部細藍條
    canvas.setFillColor(NAVY)
    canvas.rect(0, h - 1.2*cm, w, 1.2*cm, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont("NotoTC", 9)
    canvas.drawString(1.5*cm, h - 0.9*cm, "空氣品質月報")
    canvas.drawRightString(w - 1.5*cm, h - 0.9*cm,
                           f"第 {doc.page} 頁  |  AQI Monitor")

    # 底部頁碼
    canvas.setFillColor(GRAY)
    canvas.setFont("NotoTC", 8)
    canvas.drawCentredString(w/2, 0.8*cm,
        f"© {datetime.now().year} WeiMing Yu  |  資料來源：World Air Quality Index（WAQI）")

    canvas.restoreState()


# ===== 7. 主要產生函式 =====

def generate_pdf(city_keys: list, city_names: list,
                 year: int, month: int) -> bytes:
    """
    產生 PDF 月報，回傳 bytes。

    Args:
        city_keys:  WAQI 識別碼清單
        city_names: 對應的顯示名稱清單
        year:       報告年份
        month:      報告月份
    Returns:
        bytes：PDF 檔案內容
    """
    _register_fonts()
    styles = _get_styles()

    df, alert_df = _query_data(city_keys, year, month)

    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(
        buffer,
        pagesize     = A4,
        topMargin    = 2.5*cm,
        bottomMargin = 1.5*cm,
        leftMargin   = 2*cm,
        rightMargin  = 2*cm,
        title        = f"空氣品質月報 {year}/{month:02d}",
        author       = "俞威名 WeiMing Yu",
    )

    story = []
    W     = A4[0] - 4*cm   # 可用寬度

    # ---- 封面空白區（讓頁首繪製的藍色區塊有足夠空間）----
    story.append(Spacer(1, 9*cm))

    # ---- 封面資訊表 ----
    info_data = [
        ["報告期間", f"{year} 年 {month:02d} 月"],
        ["監控城市", "、".join(city_names)],
        ["資料來源", "World Air Quality Index（WAQI）"],
        ["產生時間", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        ["製作單位", "AQI Monitor"],
        ["製作人員", "俞威名（WeiMing Yu）"],
    ]
    info_table = Table(
        [[Paragraph(f"<b>{k}</b>", styles["body"]),
          Paragraph(v, styles["body"])] for k, v in info_data],
        colWidths=[4*cm, W - 4*cm]
    )
    info_table.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (0, -1), LIGHT),
        ("FONTNAME",     (0, 0), (-1, -1), "NotoTC"),
        ("FONTSIZE",     (0, 0), (-1, -1), 10),
        ("GRID",         (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 6),
    ]))
    story.append(info_table)
    story.append(PageBreak())

    # ================================================================
    # 第2頁起：各城市統計
    # ================================================================
    if df.empty:
        story.append(Paragraph("本月無資料", styles["h1"]))
    else:
        # ---- 統計摘要表 ----
        story.append(Paragraph("一、統計摘要", styles["h1"]))
        story.append(HRFlowable(width=W, color=BLUE, thickness=1.5))
        story.append(Spacer(1, 0.3*cm))

        summary_data = [["城市", "資料筆數", "AQI 平均", "AQI 最高",
                          "AQI 最低", "PM2.5 平均", "超標天數"]]
        for city_name in city_names:
            city_df  = df[df["display_name"] == city_name]
            aqi_vals = city_df["aqi"].dropna()
            daily    = city_df.groupby("date")["aqi"].mean()
            exceed   = int((daily > 100).sum())

            summary_data.append([
                city_name,
                str(len(city_df)),
                f"{aqi_vals.mean():.1f}" if len(aqi_vals) else "N/A",
                f"{aqi_vals.max():.0f}"  if len(aqi_vals) else "N/A",
                f"{aqi_vals.min():.0f}"  if len(aqi_vals) else "N/A",
                f"{city_df['pm25'].dropna().mean():.1f}" if city_df['pm25'].notna().any() else "N/A",
                f"{exceed} 天",
            ])

        story.append(_make_table(
            summary_data,
            col_widths=[4.5*cm, 2*cm, 2*cm, 2*cm, 2*cm, 2.5*cm, 2*cm]
        ))
        story.append(Spacer(1, 0.5*cm))

        # ---- 各城市詳細 ----
        story.append(Paragraph("二、各城市月度分析", styles["h1"]))
        story.append(HRFlowable(width=W, color=BLUE, thickness=1.5))

        for city_name in city_names:
            city_df  = df[df["display_name"] == city_name]
            if city_df.empty:
                continue

            aqi_vals = city_df["aqi"].dropna()
            story.append(Spacer(1, 0.4*cm))
            story.append(Paragraph(f"▍ {city_name}", styles["h2"]))

            # 城市統計小卡
            avg_aqi = aqi_vals.mean() if len(aqi_vals) else None
            lv_text = _aqi_label(avg_aqi) if avg_aqi else "無資料"
            card_data = [[
                f"月平均 AQI\n{avg_aqi:.1f}" if avg_aqi else "月平均 AQI\nN/A",
                f"最高 AQI\n{aqi_vals.max():.0f}" if len(aqi_vals) else "最高 AQI\nN/A",
                f"最低 AQI\n{aqi_vals.min():.0f}" if len(aqi_vals) else "最低 AQI\nN/A",
                f"等級\n{lv_text}",
                f"資料筆數\n{len(city_df)}",
            ]]
            card = Table(card_data, colWidths=[W/5]*5)
            card.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1, -1), LIGHT),
                ("FONTNAME",      (0, 0), (-1, -1), "NotoTC"),
                ("FONTSIZE",      (0, 0), (-1, -1), 9),
                ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
                ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING",    (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#BBBBBB")),
                ("LINEABOVE",     (0, 0), (-1, 0), 2, BLUE),
            ]))
            story.append(card)
            story.append(Spacer(1, 0.3*cm))

            # 每日資料表（最多顯示 31 天）
            daily_df = city_df.groupby("date").agg(
                AQI平均=("aqi", "mean"),
                AQI最高=("aqi", "max"),
                PM25  =("pm25", "mean"),
                PM10  =("pm10", "mean"),
            ).reset_index().head(31)

            daily_data = [["日期", "AQI 平均", "AQI 最高", "PM2.5", "PM10", "等級"]]
            for _, r in daily_df.iterrows():
                avg = r["AQI平均"]
                daily_data.append([
                    str(r["date"]),
                    f"{avg:.1f}"         if pd.notna(avg)       else "N/A",
                    f"{r['AQI最高']:.0f}" if pd.notna(r["AQI最高"]) else "N/A",
                    f"{r['PM25']:.1f}"   if pd.notna(r["PM25"])  else "N/A",
                    f"{r['PM10']:.1f}"   if pd.notna(r["PM10"])  else "N/A",
                    _aqi_label(avg)      if pd.notna(avg)       else "N/A",
                ])

            daily_table = _make_table(
                daily_data,
                col_widths=[3*cm, 2.5*cm, 2.5*cm, 2*cm, 2*cm, 3*cm]
            )
            story.append(daily_table)

        story.append(PageBreak())

        # ---- 污染物分析 ----
        story.append(Paragraph("三、污染物分析", styles["h1"]))
        story.append(HRFlowable(width=W, color=BLUE, thickness=1.5))
        story.append(Spacer(1, 0.3*cm))

        pollutant_data = [["城市", "PM2.5 均值", "PM10 均值", "NO2 均值",
                            "CO 均值", "SO2 均值", "O3 均值"]]
        for city_name in city_names:
            city_df = df[df["display_name"] == city_name]
            def avg(col):
                v = city_df[col].dropna()
                return f"{v.mean():.1f}" if len(v) else "N/A"
            pollutant_data.append([
                city_name, avg("pm25"), avg("pm10"),
                avg("no2"), avg("co"), avg("so2"), avg("o3"),
            ])

        story.append(_make_table(
            pollutant_data,
            col_widths=[4*cm, 2*cm, 2*cm, 2*cm, 2*cm, 2*cm, 2*cm]
        ))

    # ---- 觸發記錄 ----
    story.append(Spacer(1, 0.8*cm))
    story.append(Paragraph("四、AQI 觸發事件記錄", styles["h1"]))
    story.append(HRFlowable(width=W, color=BLUE, thickness=1.5))
    story.append(Spacer(1, 0.3*cm))

    if alert_df.empty:
        story.append(Paragraph("本月無觸發事件記錄。", styles["body"]))
    else:
        alert_data = [["觸發時間", "城市", "AQI", "閾值", "Webhook 狀態"]]
        for _, r in alert_df.iterrows():
            alert_data.append([
                r.get("triggered_at", "")[:16],
                r.get("display_name", ""),
                str(int(r["aqi"])) if pd.notna(r.get("aqi")) else "N/A",
                str(int(r["threshold"])) if pd.notna(r.get("threshold")) else "N/A",
                r.get("webhook_status", ""),
            ])
        story.append(_make_table(
            alert_data,
            col_widths=[4.5*cm, 4*cm, 2*cm, 2*cm, 2.5*cm]
        ))

    # ---- 免責聲明 ----
    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(width=W, color=GRAY, thickness=0.5))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        "本報告資料來源為 World Air Quality Index（WAQI）免費 API，每 30 分鐘自動抓取一次。"
        "資料僅供參考，如需精確數據請以當地環保機關公告為準。",
        styles["caption"]
    ))
    story.append(Paragraph(
        f"報告產生時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}　　"
        f"製作：俞威名（WeiMing Yu）",
        styles["footer"]
    ))

    # ---- 建立 PDF ----
    doc.build(
        story,
        onFirstPage  = _on_first_page,
        onLaterPages = _on_later_pages,
    )

    buffer.seek(0)
    return buffer.getvalue()
