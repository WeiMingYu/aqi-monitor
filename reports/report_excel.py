"""
reports/report_excel.py - Excel 月報產生模組
功能：從 aqi_history 撈資料，產生格式化的 Excel 月報
包含：統計摘要、每日資料、每小時分析、污染物明細、觸發記錄
"""

import os
import io
from datetime import datetime, date
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import (
    Font, PatternFill, Alignment, Border, Side, GradientFill
)
from openpyxl.utils import get_column_letter
from openpyxl.chart import LineChart, BarChart, Reference

from core.db_init import get_conn


# ===== 1. 樣式常數 =====
C_HEADER_BG  = "1F4E79"   # 深藍（標題列背景）
C_HEADER_FG  = "FFFFFF"   # 白（標題列文字）
C_SUB_BG     = "2E75B6"   # 中藍（副標題）
C_ROW1       = "D6E4F0"   # 淺藍（奇數列）
C_ROW2       = "FFFFFF"   # 白（偶數列）
C_GOOD       = "00B050"   # 綠（AQI 優良）
C_OK         = "FFFF00"   # 黃（AQI 普通）
C_WARN       = "FFC000"   # 橘（AQI 敏感）
C_BAD        = "FF0000"   # 紅（AQI 不健康）
C_VERY_BAD   = "7030A0"   # 紫（非常不健康）

FONT_NAME    = "微軟正黑體"

# ===== 2. 工具函式 =====

def _hdr_font(bold=True, size=11, color=C_HEADER_FG):
    return Font(name=FONT_NAME, bold=bold, size=size, color=color)

def _body_font(bold=False, size=10, color="1F1F1F"):
    return Font(name=FONT_NAME, bold=bold, size=size, color=color)

def _fill(hex_color):
    return PatternFill("solid", fgColor=hex_color)

def _center():
    return Alignment(horizontal="center", vertical="center", wrap_text=True)

def _left():
    return Alignment(horizontal="left", vertical="center", wrap_text=True)

def _border():
    s = Side(style="thin", color="AAAAAA")
    return Border(left=s, right=s, top=s, bottom=s)

def _aqi_fill(aqi_val):
    """依 AQI 值回傳對應的儲存格背景色"""
    try:
        v = float(aqi_val)
    except (TypeError, ValueError):
        return None
    if v <= 50:   return _fill("CCFFCC")   # 淺綠
    if v <= 100:  return _fill("FFFFCC")   # 淺黃
    if v <= 150:  return _fill("FFE5CC")   # 淺橘
    if v <= 200:  return _fill("FFCCCC")   # 淺紅
    if v <= 300:  return _fill("E5CCFF")   # 淺紫
    return _fill("FFCCDD")                  # 深紅

def _set_col_widths(ws, widths: dict):
    """設定欄寬，widths = { 'A': 15, 'B': 20, ... }"""
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

def _write_header_row(ws, row, cols, bg=C_HEADER_BG):
    """寫入標題列"""
    for c, text in enumerate(cols, 1):
        cell = ws.cell(row=row, column=c, value=text)
        cell.font      = _hdr_font()
        cell.fill      = _fill(bg)
        cell.alignment = _center()
        cell.border    = _border()


# ===== 3. 查詢資料 =====

def _query_month_data(city_keys: list, year: int, month: int) -> pd.DataFrame:
    """
    查詢指定城市清單、指定月份的 aqi_history 資料。
    Returns:
        DataFrame，含 display_name 欄位
    """
    placeholders = ",".join(["?"] * len(city_keys))
    month_str    = f"{year}-{month:02d}"

    conn = get_conn()
    df   = pd.read_sql_query(f"""
        SELECT h.city_key, w.display_name,
               h.fetch_time, h.aqi, h.pm25, h.pm10,
               h.no2, h.co, h.so2, h.o3,
               h.temp, h.humidity, h.wind, h.pressure
        FROM   aqi_history h
        JOIN   watch_list   w ON h.city_key = w.city_key
        WHERE  h.city_key IN ({placeholders})
          AND  strftime('%Y-%m', h.fetch_time) = ?
        ORDER  BY h.city_key, h.fetch_time
    """, conn, params=city_keys + [month_str])
    conn.close()

    if df.empty:
        return df

    df["fetch_time"] = pd.to_datetime(df["fetch_time"])
    df["date"]       = df["fetch_time"].dt.date
    df["hour"]       = df["fetch_time"].dt.hour
    return df


def _query_alert_data(city_keys: list, year: int, month: int) -> pd.DataFrame:
    """查詢指定城市、指定月份的 alert_log 資料"""
    placeholders = ",".join(["?"] * len(city_keys))
    month_str    = f"{year}-{month:02d}"

    conn = get_conn()
    df   = pd.read_sql_query(f"""
        SELECT city_key, display_name, aqi, threshold,
               webhook_status, triggered_at
        FROM   alert_log
        WHERE  city_key IN ({placeholders})
          AND  strftime('%Y-%m', triggered_at) = ?
        ORDER  BY triggered_at
    """, conn, params=city_keys + [month_str])
    conn.close()
    return df


# ===== 4. 工作表：封面 =====

def _sheet_cover(wb: Workbook, city_names: list, year: int, month: int):
    ws = wb.active
    ws.title = "封面"
    ws.sheet_view.showGridLines = False

    # 標題區
    ws.merge_cells("A1:H1")
    ws["A1"] = "空氣品質月報"
    ws["A1"].font      = Font(name=FONT_NAME, bold=True, size=24, color=C_HEADER_FG)
    ws["A1"].fill      = _fill(C_HEADER_BG)
    ws["A1"].alignment = _center()
    ws.row_dimensions[1].height = 50

    ws.merge_cells("A2:H2")
    ws["A2"] = f"Air Quality Monthly Report — {year} 年 {month:02d} 月"
    ws["A2"].font      = Font(name=FONT_NAME, size=14, color=C_HEADER_FG)
    ws["A2"].fill      = _fill(C_SUB_BG)
    ws["A2"].alignment = _center()
    ws.row_dimensions[2].height = 30

    # 基本資訊
    info_rows = [
        ("報告期間", f"{year} 年 {month:02d} 月"),
        ("監控城市", "、".join(city_names)),
        ("資料來源", "World Air Quality Index（WAQI）"),
        ("產生時間", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ("製作單位", "AQI Monitor"),
        ("製作人員", "俞威名（WeiMing Yu）"),
    ]
    for i, (label, value) in enumerate(info_rows, 4):
        ws.merge_cells(f"B{i}:C{i}")
        ws.merge_cells(f"D{i}:H{i}")
        ws[f"B{i}"] = label
        ws[f"D{i}"] = value
        ws[f"B{i}"].font      = _body_font(bold=True)
        ws[f"D{i}"].font      = _body_font()
        ws[f"B{i}"].fill      = _fill(C_ROW1)
        ws[f"D{i}"].fill      = _fill(C_ROW2)
        ws[f"B{i}"].alignment = _center()
        ws[f"D{i}"].alignment = _left()
        ws.row_dimensions[i].height = 22

    _set_col_widths(ws, {"A": 3, "B": 12, "C": 5, "D": 15, "E": 15,
                          "F": 15, "G": 15, "H": 15})


# ===== 5. 工作表：統計摘要 =====

def _sheet_summary(wb: Workbook, df: pd.DataFrame, year: int, month: int):
    ws = wb.create_sheet("統計摘要")
    ws.sheet_view.showGridLines = False

    # 標題
    ws.merge_cells("A1:I1")
    ws["A1"] = f"{year}/{month:02d} 空氣品質統計摘要"
    ws["A1"].font      = _hdr_font(size=14)
    ws["A1"].fill      = _fill(C_HEADER_BG)
    ws["A1"].alignment = _center()
    ws.row_dimensions[1].height = 30

    # 欄位標題
    headers = ["城市", "資料筆數", "AQI 平均", "AQI 最高", "AQI 最低",
               "PM2.5 平均", "PM10 平均", "超標天數\n(AQI>100)", "優良天數\n(AQI≤50)"]
    _write_header_row(ws, 2, headers)
    ws.row_dimensions[2].height = 30

    # 各城市統計
    row = 3
    for city_name in df["display_name"].unique():
        city_df = df[df["display_name"] == city_name]
        aqi_vals = city_df["aqi"].dropna()

        # 計算超標/優良天數（以日為單位）
        daily_avg = city_df.groupby("date")["aqi"].mean()
        exceed_days = int((daily_avg > 100).sum())
        good_days   = int((daily_avg <= 50).sum())

        data = [
            city_name,
            len(city_df),
            f"{aqi_vals.mean():.1f}" if len(aqi_vals) else "N/A",
            f"{aqi_vals.max():.0f}"  if len(aqi_vals) else "N/A",
            f"{aqi_vals.min():.0f}"  if len(aqi_vals) else "N/A",
            f"{city_df['pm25'].dropna().mean():.1f}" if city_df['pm25'].notna().any() else "N/A",
            f"{city_df['pm10'].dropna().mean():.1f}" if city_df['pm10'].notna().any() else "N/A",
            exceed_days,
            good_days,
        ]

        bg = C_ROW1 if row % 2 == 0 else C_ROW2
        for c, val in enumerate(data, 1):
            cell = ws.cell(row=row, column=c, value=val)
            cell.font      = _body_font()
            cell.fill      = _fill(bg)
            cell.alignment = _center() if c > 1 else _left()
            cell.border    = _border()
            # AQI 平均著色
            if c == 3 and val != "N/A":
                aqi_fill = _aqi_fill(val)
                if aqi_fill:
                    cell.fill = aqi_fill

        ws.row_dimensions[row].height = 20
        row += 1

    _set_col_widths(ws, {
        "A": 22, "B": 10, "C": 10, "D": 10, "E": 10,
        "F": 12, "G": 12, "H": 14, "I": 14,
    })


# ===== 6. 工作表：每日資料（每個城市一個 sheet）=====

def _sheet_daily(wb: Workbook, df: pd.DataFrame, city_name: str):
    safe_name = city_name[:20]   # sheet 名稱最長 31 字元
    ws = wb.create_sheet(f"{safe_name}_每日")
    ws.sheet_view.showGridLines = False

    city_df  = df[df["display_name"] == city_name].copy()
    daily_df = city_df.groupby("date").agg(
        AQI平均   = ("aqi",      "mean"),
        AQI最高   = ("aqi",      "max"),
        AQI最低   = ("aqi",      "min"),
        PM25平均  = ("pm25",     "mean"),
        PM10平均  = ("pm10",     "mean"),
        NO2平均   = ("no2",      "mean"),
        O3平均    = ("o3",       "mean"),
        資料筆數  = ("aqi",      "count"),
    ).reset_index()

    # 標題
    ws.merge_cells("A1:I1")
    ws["A1"] = f"{city_name} — 每日 AQI 統計"
    ws["A1"].font      = _hdr_font(size=13)
    ws["A1"].fill      = _fill(C_HEADER_BG)
    ws["A1"].alignment = _center()
    ws.row_dimensions[1].height = 28

    headers = ["日期", "AQI 平均", "AQI 最高", "AQI 最低",
               "PM2.5", "PM10", "NO₂", "O₃", "資料筆數"]
    _write_header_row(ws, 2, headers)
    ws.row_dimensions[2].height = 22

    for i, row_data in daily_df.iterrows():
        r = i + 3
        bg = C_ROW1 if r % 2 == 0 else C_ROW2

        vals = [
            str(row_data["date"]),
            round(row_data["AQI平均"],  1) if pd.notna(row_data["AQI平均"])  else "",
            round(row_data["AQI最高"],  0) if pd.notna(row_data["AQI最高"])  else "",
            round(row_data["AQI最低"],  0) if pd.notna(row_data["AQI最低"])  else "",
            round(row_data["PM25平均"], 1) if pd.notna(row_data["PM25平均"]) else "",
            round(row_data["PM10平均"], 1) if pd.notna(row_data["PM10平均"]) else "",
            round(row_data["NO2平均"],  1) if pd.notna(row_data["NO2平均"])  else "",
            round(row_data["O3平均"],   1) if pd.notna(row_data["O3平均"])   else "",
            int(row_data["資料筆數"]),
        ]
        for c, val in enumerate(vals, 1):
            cell = ws.cell(row=r, column=c, value=val)
            cell.font      = _body_font()
            cell.fill      = _fill(bg)
            cell.alignment = _center() if c > 1 else _left()
            cell.border    = _border()
            # AQI 平均著色
            if c == 2 and val != "":
                aqi_fill = _aqi_fill(val)
                if aqi_fill:
                    cell.fill = aqi_fill
        ws.row_dimensions[r].height = 18

    # 加總列
    total_row = len(daily_df) + 3
    ws.cell(total_row, 1, "月平均").font = _hdr_font()
    ws.cell(total_row, 1).fill = _fill(C_SUB_BG)
    ws.cell(total_row, 1).alignment = _center()

    for c_idx, col in enumerate(["AQI平均", "PM25平均", "PM10平均", "NO2平均", "O3平均"], 2):
        col_letter = get_column_letter(c_idx)
        formula    = f"=AVERAGE({col_letter}3:{col_letter}{total_row-1})"
        cell       = ws.cell(total_row, c_idx, formula)
        cell.font  = _hdr_font()
        cell.fill  = _fill(C_SUB_BG)
        cell.alignment = _center()
        cell.number_format = "0.0"

    _set_col_widths(ws, {
        "A": 14, "B": 10, "C": 10, "D": 10,
        "E": 10, "F": 10, "G": 10, "H": 10, "I": 10,
    })


# ===== 7. 工作表：原始資料 =====

def _sheet_raw(wb: Workbook, df: pd.DataFrame, city_name: str):
    safe_name = city_name[:20]
    ws = wb.create_sheet(f"{safe_name}_原始")
    ws.sheet_view.showGridLines = False

    city_df = df[df["display_name"] == city_name].copy()
    city_df["fetch_time"] = city_df["fetch_time"].dt.strftime("%Y-%m-%d %H:%M:%S")

    headers = ["抓取時間", "AQI", "PM2.5", "PM10", "NO₂",
               "CO", "SO₂", "O₃", "溫度", "濕度", "風速", "氣壓"]
    cols    = ["fetch_time", "aqi", "pm25", "pm10", "no2",
               "co", "so2", "o3", "temp", "humidity", "wind", "pressure"]

    # 標題
    ws.merge_cells(f"A1:{get_column_letter(len(headers))}1")
    ws["A1"] = f"{city_name} — 原始資料"
    ws["A1"].font      = _hdr_font(size=12)
    ws["A1"].fill      = _fill(C_HEADER_BG)
    ws["A1"].alignment = _center()
    ws.row_dimensions[1].height = 25

    _write_header_row(ws, 2, headers)

    for i, (_, row_data) in enumerate(city_df[cols].iterrows()):
        r  = i + 3
        bg = C_ROW1 if r % 2 == 0 else C_ROW2
        for c, val in enumerate(row_data, 1):
            cell           = ws.cell(row=r, column=c, value=val)
            cell.font      = _body_font(size=9)
            cell.fill      = _fill(bg)
            cell.alignment = _center() if c > 1 else _left()
            cell.border    = _border()
        ws.row_dimensions[r].height = 16

    _set_col_widths(ws, {
        "A": 20, "B": 8, "C": 8, "D": 8, "E": 8,
        "F": 8, "G": 8, "H": 8, "I": 8, "J": 8, "K": 8, "L": 8,
    })


# ===== 8. 工作表：觸發記錄 =====

def _sheet_alerts(wb: Workbook, alert_df: pd.DataFrame):
    ws = wb.create_sheet("觸發記錄")
    ws.sheet_view.showGridLines = False

    ws.merge_cells("A1:F1")
    ws["A1"] = "AQI 觸發事件記錄"
    ws["A1"].font      = _hdr_font(size=13)
    ws["A1"].fill      = _fill(C_HEADER_BG)
    ws["A1"].alignment = _center()
    ws.row_dimensions[1].height = 28

    if alert_df.empty:
        ws["A2"] = "本月無觸發記錄"
        ws["A2"].font = _body_font()
        return

    headers = ["觸發時間", "城市", "AQI", "閾值", "Webhook 狀態", "回應"]
    _write_header_row(ws, 2, headers)

    for i, row_data in alert_df.iterrows():
        r  = i + 3
        bg = C_ROW1 if r % 2 == 0 else C_ROW2

        status_color = {
            "sent":    "CCFFCC",
            "skipped": "F0F0F0",
            "failed":  "FFCCCC",
        }.get(row_data.get("webhook_status", ""), C_ROW2)

        vals = [
            row_data.get("triggered_at", ""),
            row_data.get("display_name", ""),
            row_data.get("aqi", ""),
            row_data.get("threshold", ""),
            row_data.get("webhook_status", ""),
            "",   # webhook_response 省略（太長）
        ]
        for c, val in enumerate(vals, 1):
            cell = ws.cell(row=r, column=c, value=val)
            cell.font      = _body_font()
            cell.fill      = _fill(status_color) if c >= 5 else _fill(bg)
            cell.alignment = _center() if c > 1 else _left()
            cell.border    = _border()
        ws.row_dimensions[r].height = 18

    _set_col_widths(ws, {
        "A": 20, "B": 22, "C": 8, "D": 8, "E": 14, "F": 20,
    })


# ===== 9. 主要產生函式 =====

def generate_excel(city_keys: list, city_names: list,
                   year: int, month: int) -> bytes:
    """
    產生 Excel 月報，回傳 bytes（供 Streamlit download_button 使用）。

    Args:
        city_keys:  WAQI 識別碼清單
        city_names: 對應的顯示名稱清單
        year:       報告年份
        month:      報告月份
    Returns:
        bytes：Excel 檔案內容
    """
    # ---- 9-1. 查詢資料 ----
    df       = _query_month_data(city_keys, year, month)
    alert_df = _query_alert_data(city_keys, year, month)

    # ---- 9-2. 建立 Workbook ----
    wb = Workbook()

    # ---- 9-3. 封面 ----
    _sheet_cover(wb, city_names, year, month)

    # ---- 9-4. 統計摘要 ----
    if not df.empty:
        _sheet_summary(wb, df, year, month)

        # ---- 9-5. 每個城市的每日資料 + 原始資料 ----
        for city_name in city_names:
            if city_name in df["display_name"].values:
                _sheet_daily(wb, df, city_name)
                _sheet_raw(wb, df, city_name)

    # ---- 9-6. 觸發記錄 ----
    _sheet_alerts(wb, alert_df)

    # ---- 9-7. 回傳 bytes ----
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
