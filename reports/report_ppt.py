"""
reports/report_ppt.py - PPT 月報產生模組
功能：從 aqi_history 撈資料，產生格式化的 PPT 月報（會員簡報版）
使用 python-pptx + 微軟正黑體，配合品牌色
投影片結構：
  Slide 1  : 封面
  Slide 2  : 目錄
  Slide 3  : 統計摘要
  Slide 4+ : 各城市月度分析（每城市一張）
  最後一張 : 觸發事件記錄
"""

import io
from datetime import datetime
import pandas as pd

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt
from pptx.chart.data import ChartData
from pptx.enum.chart import XL_CHART_TYPE

from core.db_init import get_conn


# ===== 1. 色彩常數 =====
C_NAVY   = RGBColor(0x1F, 0x4E, 0x79)   # 深藍
C_BLUE   = RGBColor(0x2E, 0x75, 0xB6)   # 中藍
C_ACCENT = RGBColor(0x2B, 0x57, 0x97)   # 強調藍
C_LIGHT  = RGBColor(0xD6, 0xE4, 0xF0)   # 淺藍
C_WHITE  = RGBColor(0xFF, 0xFF, 0xFF)
C_BLACK  = RGBColor(0x1F, 0x1F, 0x1F)
C_GRAY   = RGBColor(0x8A, 0x9B, 0xB0)

C_AQI_GOOD    = RGBColor(0x00, 0xE4, 0x00)
C_AQI_OK      = RGBColor(0xFF, 0xD7, 0x00)
C_AQI_WARN    = RGBColor(0xFF, 0x7E, 0x00)
C_AQI_BAD     = RGBColor(0xFF, 0x00, 0x00)
C_AQI_VERYBAD = RGBColor(0x8F, 0x3F, 0x97)

FONT = "微軟正黑體"
SLIDE_W = Inches(13.33)   # 寬螢幕 16:9
SLIDE_H = Inches(7.5)


# ===== 2. 工具函式 =====

def _rgb(hex_str: str) -> RGBColor:
    """#RRGGBB → RGBColor"""
    h = hex_str.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

def _aqi_color(aqi_val) -> RGBColor:
    """依 AQI 值回傳顏色"""
    try:
        v = float(aqi_val)
    except (TypeError, ValueError):
        return C_GRAY
    if v <= 50:   return C_AQI_GOOD
    if v <= 100:  return C_AQI_OK
    if v <= 150:  return C_AQI_WARN
    if v <= 200:  return C_AQI_BAD
    return C_AQI_VERYBAD

def _aqi_label(aqi_val) -> str:
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

def _add_rect(slide, left, top, width, height, fill_color, line_color=None):
    """加入填色矩形"""
    shape = slide.shapes.add_shape(
        1,  # MSO_SHAPE_TYPE.RECTANGLE
        Inches(left), Inches(top), Inches(width), Inches(height)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    if line_color:
        shape.line.color.rgb = line_color
    else:
        shape.line.fill.background()
    return shape

def _add_text(slide, text, left, top, width, height,
              font_size=14, bold=False, color=C_BLACK,
              align=PP_ALIGN.LEFT, font_name=FONT, italic=False):
    """加入文字方塊"""
    txBox = slide.shapes.add_textbox(
        Inches(left), Inches(top), Inches(width), Inches(height)
    )
    tf = txBox.text_frame
    tf.word_wrap = True
    p  = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = str(text)
    run.font.name    = font_name
    run.font.size    = Pt(font_size)
    run.font.bold    = bold
    run.font.italic  = italic
    run.font.color.rgb = color
    return txBox

def _add_table(slide, data, left, top, width, height,
               col_widths=None, header_bg=None):
    """
    加入表格。
    data: list of list（第一列為標題）
    col_widths: 各欄寬度比例（None=均分）
    """
    rows = len(data)
    cols = len(data[0])

    tbl = slide.shapes.add_table(
        rows, cols,
        Inches(left), Inches(top),
        Inches(width), Inches(height)
    ).table

    # 欄寬設定
    if col_widths:
        total = sum(col_widths)
        for i, w in enumerate(col_widths):
            tbl.columns[i].width = int(Inches(width) * w / total)

    # 填入資料
    for r, row in enumerate(data):
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            cell.text = str(val) if val is not None else ""

            # 字型
            for para in cell.text_frame.paragraphs:
                para.alignment = PP_ALIGN.CENTER if c > 0 else PP_ALIGN.LEFT
                for run in para.runs:
                    run.font.name = FONT
                    run.font.size = Pt(9) if r > 0 else Pt(10)
                    run.font.bold = (r == 0)
                    run.font.color.rgb = C_WHITE if r == 0 else C_BLACK

            # 標題列背景
            if r == 0:
                bg = header_bg or C_NAVY
                cell.fill.solid()
                cell.fill.fore_color.rgb = bg
            elif r % 2 == 0:
                cell.fill.solid()
                cell.fill.fore_color.rgb = C_LIGHT

    return tbl


# ===== 3. 查詢資料 =====

def _query_data(city_keys: list, year: int, month: int):
    placeholders = ",".join(["?"] * len(city_keys))
    month_str    = f"{year}-{month:02d}"

    conn = get_conn()
    df   = pd.read_sql_query(f"""
        SELECT h.city_key, w.display_name,
               h.fetch_time, h.aqi, h.pm25, h.pm10,
               h.no2, h.o3, h.temp, h.humidity
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


# ===== 4. 各投影片 =====

def _slide_cover(prs: Presentation, city_names: list, year: int, month: int):
    """Slide 1：封面"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # 空白版面

    # 深藍背景
    _add_rect(slide, 0, 0, 13.33, 7.5, C_NAVY)

    # 左側裝飾色塊
    _add_rect(slide, 0, 0, 0.4, 7.5, C_BLUE)

    # 主標題
    _add_text(slide, "空氣品質月報",
              1, 1.8, 11, 1.5,
              font_size=40, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)

    # 副標題
    _add_text(slide, "Air Quality Monthly Report",
              1, 3.2, 11, 0.8,
              font_size=18, color=C_LIGHT, align=PP_ALIGN.CENTER, italic=True)

    # 期間
    _add_text(slide, f"{year} 年 {month:02d} 月",
              1, 4.0, 11, 0.7,
              font_size=22, bold=True, color=C_AQI_OK, align=PP_ALIGN.CENTER)

    # 城市清單
    _add_text(slide, f"監控城市：{'  ｜  '.join(city_names)}",
              1, 4.8, 11, 0.6,
              font_size=13, color=C_LIGHT, align=PP_ALIGN.CENTER)

    # 底部資訊
    _add_text(slide,
              f"製作：俞威名（WeiMing Yu）  ｜  {datetime.now().strftime('%Y-%m-%d')}",
              1, 6.6, 11, 0.5,
              font_size=10, color=C_GRAY, align=PP_ALIGN.CENTER)


def _slide_toc(prs: Presentation, city_names: list):
    """Slide 2：目錄"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    # 頂部標題列
    _add_rect(slide, 0, 0, 13.33, 1.1, C_NAVY)
    _add_text(slide, "目  錄", 0.3, 0.1, 12, 0.9,
              font_size=24, bold=True, color=C_WHITE)

    items = [
        "一、統計摘要",
    ] + [f"二-{i+1}、{name} 月度分析" for i, name in enumerate(city_names)] + [
        f"{'三' if len(city_names) == 1 else str(len(city_names)+2)}、觸發事件記錄",
    ]

    for i, item in enumerate(items):
        y = 1.4 + i * 0.65
        # 數字圓圈背景
        _add_rect(slide, 0.5, y, 0.5, 0.45, C_BLUE)
        _add_text(slide, str(i+1), 0.5, y, 0.5, 0.45,
                  font_size=13, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
        _add_text(slide, item, 1.2, y, 10, 0.45,
                  font_size=14, color=C_BLACK)


def _slide_summary(prs: Presentation, df: pd.DataFrame,
                   city_names: list, year: int, month: int):
    """Slide 3：統計摘要"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    _add_rect(slide, 0, 0, 13.33, 1.1, C_NAVY)
    _add_text(slide, f"統計摘要  —  {year}/{month:02d}", 0.3, 0.1, 12, 0.9,
              font_size=22, bold=True, color=C_WHITE)

    if df.empty:
        _add_text(slide, "本月無資料", 0.5, 1.5, 12, 1,
                  font_size=16, color=C_GRAY)
        return

    # 每個城市一個統計卡片
    card_w = 12.0 / len(city_names)
    for i, city_name in enumerate(city_names):
        city_df  = df[df["display_name"] == city_name]
        aqi_vals = city_df["aqi"].dropna()
        avg_aqi  = aqi_vals.mean() if len(aqi_vals) else None
        daily    = city_df.groupby("date")["aqi"].mean() if not city_df.empty else pd.Series()
        exceed   = int((daily > 100).sum()) if len(daily) else 0

        x = 0.5 + i * card_w
        # 卡片背景
        _add_rect(slide, x, 1.3, card_w - 0.15, 5.6, C_LIGHT)

        # 城市名
        _add_text(slide, city_name, x + 0.1, 1.4, card_w - 0.35, 0.6,
                  font_size=14, bold=True, color=C_NAVY, align=PP_ALIGN.CENTER)

        # AQI 大數字
        aqi_clr  = _aqi_color(avg_aqi)
        aqi_disp = f"{avg_aqi:.1f}" if avg_aqi is not None else "N/A"
        _add_text(slide, aqi_disp, x + 0.1, 2.0, card_w - 0.35, 1.2,
                  font_size=48, bold=True, color=aqi_clr, align=PP_ALIGN.CENTER)

        # 等級
        lv_text = _aqi_label(avg_aqi)
        _add_text(slide, lv_text, x + 0.1, 3.1, card_w - 0.35, 0.5,
                  font_size=12, color=aqi_clr, align=PP_ALIGN.CENTER)

        # 統計小字
        stats = [
            ("最高", f"{aqi_vals.max():.0f}" if len(aqi_vals) else "N/A"),
            ("最低", f"{aqi_vals.min():.0f}" if len(aqi_vals) else "N/A"),
            ("超標天數", f"{exceed} 天"),
            ("資料筆數", f"{len(city_df)} 筆"),
            ("PM2.5 均值", f"{city_df['pm25'].dropna().mean():.1f}" if city_df['pm25'].notna().any() else "N/A"),
        ]
        for j, (label, val) in enumerate(stats):
            y = 3.7 + j * 0.46
            _add_text(slide, label, x + 0.15, y, card_w * 0.5, 0.4,
                      font_size=10, color=C_GRAY)
            _add_text(slide, val,   x + card_w * 0.5, y, card_w * 0.45, 0.4,
                      font_size=10, bold=True, color=C_NAVY, align=PP_ALIGN.RIGHT)


def _slide_city(prs: Presentation, df: pd.DataFrame,
                city_name: str, year: int, month: int):
    """各城市月度分析投影片"""
    slide    = prs.slides.add_slide(prs.slide_layouts[6])
    city_df  = df[df["display_name"] == city_name].copy()
    aqi_vals = city_df["aqi"].dropna()
    avg_aqi  = aqi_vals.mean() if len(aqi_vals) else None

    # 標題列
    _add_rect(slide, 0, 0, 13.33, 1.1, C_NAVY)
    _add_text(slide, f"{city_name}  —  {year}/{month:02d} 月度分析",
              0.3, 0.1, 12, 0.9,
              font_size=20, bold=True, color=C_WHITE)

    # 左側：統計卡片
    _add_rect(slide, 0.3, 1.3, 3.5, 5.6, C_LIGHT)
    _add_text(slide, "月平均 AQI", 0.4, 1.4, 3.3, 0.5,
              font_size=11, color=C_GRAY, align=PP_ALIGN.CENTER)
    aqi_clr  = _aqi_color(avg_aqi)
    aqi_disp = f"{avg_aqi:.1f}" if avg_aqi is not None else "N/A"
    _add_text(slide, aqi_disp, 0.4, 1.85, 3.3, 1.1,
              font_size=52, bold=True, color=aqi_clr, align=PP_ALIGN.CENTER)
    _add_text(slide, _aqi_label(avg_aqi), 0.4, 2.9, 3.3, 0.5,
              font_size=12, color=aqi_clr, align=PP_ALIGN.CENTER)

    # 污染物統計
    def avg(col):
        v = city_df[col].dropna()
        return f"{v.mean():.1f}" if len(v) else "N/A"

    stats = [
        ("最高 AQI",   f"{aqi_vals.max():.0f}" if len(aqi_vals) else "N/A"),
        ("最低 AQI",   f"{aqi_vals.min():.0f}" if len(aqi_vals) else "N/A"),
        ("PM2.5 均值", avg("pm25")),
        ("PM10 均值",  avg("pm10")),
        ("NO₂ 均值",   avg("no2")),
        ("O₃ 均值",    avg("o3")),
    ]
    for j, (label, val) in enumerate(stats):
        y = 3.5 + j * 0.53
        _add_text(slide, label, 0.4,  y, 1.8, 0.45, font_size=10, color=C_GRAY)
        _add_text(slide, val,   2.2,  y, 1.4, 0.45,
                  font_size=10, bold=True, color=C_NAVY, align=PP_ALIGN.RIGHT)

    # 右側：每日 AQI 表格
    if not city_df.empty:
        daily_df = city_df.groupby("date").agg(
            AQI平均=("aqi", "mean"),
            AQI最高=("aqi", "max"),
            PM25   =("pm25", "mean"),
        ).reset_index().head(20)

        tbl_data = [["日期", "AQI 均", "AQI 高", "PM2.5", "等級"]]
        for _, r in daily_df.iterrows():
            avg_v = r["AQI平均"]
            tbl_data.append([
                str(r["date"]),
                f"{avg_v:.1f}"       if pd.notna(avg_v)    else "N/A",
                f"{r['AQI最高']:.0f}" if pd.notna(r["AQI最高"]) else "N/A",
                f"{r['PM25']:.1f}"   if pd.notna(r["PM25"])  else "N/A",
                _aqi_label(avg_v)[:4] if pd.notna(avg_v)    else "N/A",
            ])

        _add_table(slide, tbl_data,
                   left=4.1, top=1.3, width=8.9, height=5.6,
                   col_widths=[2.5, 1.5, 1.5, 1.5, 2.0])


def _slide_alerts(prs: Presentation, alert_df: pd.DataFrame,
                  year: int, month: int):
    """觸發事件記錄投影片"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    _add_rect(slide, 0, 0, 13.33, 1.1, C_NAVY)
    _add_text(slide, f"AQI 觸發事件記錄  —  {year}/{month:02d}",
              0.3, 0.1, 12, 0.9,
              font_size=20, bold=True, color=C_WHITE)

    if alert_df.empty:
        _add_rect(slide, 0.5, 1.5, 12.3, 2, C_LIGHT)
        _add_text(slide, "✅  本月無觸發事件記錄",
                  0.5, 1.8, 12.3, 1,
                  font_size=18, color=C_NAVY, align=PP_ALIGN.CENTER)
        return

    tbl_data = [["觸發時間", "城市", "AQI", "閾值", "Webhook 狀態"]]
    for _, r in alert_df.head(15).iterrows():
        tbl_data.append([
            str(r.get("triggered_at", ""))[:16],
            r.get("display_name", ""),
            str(int(r["aqi"])) if pd.notna(r.get("aqi")) else "N/A",
            str(int(r["threshold"])) if pd.notna(r.get("threshold")) else "N/A",
            r.get("webhook_status", ""),
        ])

    _add_table(slide, tbl_data,
               left=0.5, top=1.3, width=12.3, height=5.6,
               col_widths=[3.5, 3.0, 1.5, 1.5, 2.5])


# ===== 5. 主要產生函式 =====

def generate_ppt(city_keys: list, city_names: list,
                 year: int, month: int) -> bytes:
    """
    產生 PPT 月報，回傳 bytes。

    Args:
        city_keys:  WAQI 識別碼清單
        city_names: 對應的顯示名稱清單
        year:       報告年份
        month:      報告月份
    Returns:
        bytes：PPTX 檔案內容
    """
    df, alert_df = _query_data(city_keys, year, month)

    # 建立 16:9 簡報
    prs = Presentation()
    prs.slide_width  = SLIDE_W
    prs.slide_height = SLIDE_H

    # ---- 各投影片 ----
    _slide_cover(prs, city_names, year, month)
    _slide_toc(prs, city_names)
    _slide_summary(prs, df, city_names, year, month)

    for city_name in city_names:
        _slide_city(prs, df, city_name, year, month)

    _slide_alerts(prs, alert_df, year, month)

    # ---- 回傳 bytes ----
    buffer = io.BytesIO()
    prs.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
