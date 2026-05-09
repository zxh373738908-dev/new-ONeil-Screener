import pandas as pd
import numpy as np
import gspread
from google.oauth2.service_account import Credentials
import datetime, warnings, logging, requests, time
import yfinance as yf

# ================= 配置区 =================
warnings.filterwarnings('ignore')
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

SS_KEY = "14v3_Rm60BsZtpyAY87urGsqPO00erUQT4lNZJjUDyK8"
CREDS_FILE = "credentials.json"
TARGET_SHEET_NAME = "A-v7-V53.3-BloodBird"
TZ_SHANGHAI = datetime.timezone(datetime.timedelta(hours=8))
START_DATE_REF = "2025-12-31" 
# ==========================================

def init_sheet():
    try:
        creds = Credentials.from_service_account_file(CREDS_FILE, scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        client = gspread.authorize(creds)
        return client.open_by_key(SS_KEY).worksheet(TARGET_SHEET_NAME)
    except Exception as e:
        print(f"❌ 授权失败: {e}")
        return None

def run_v60_pro():
    start_time = time.time()
    now = datetime.datetime.now(TZ_SHANGHAI)
    update_str = now.strftime('%Y-%m-%d %H:%M')
    print(f"[{update_str}] 🚀 启动 V60.25 离线绘图增强版...")

    # 1. 扫描池子
    tv_url = "https://scanner.tradingview.com/china/scan"
    headers = {'User-Agent': 'Mozilla/5.0'}
    payload = {
        "columns": ["name", "industry", "market_cap_basic"],
        "filter":[{"left": "market_cap_basic", "operation": "greater", "right": 85e8}], 
        "range": [0, 800],
        "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"}
    }
    
    try:
        raw_data = requests.post(tv_url, json=payload, headers=headers, timeout=20).json().get('data', [])
    except: return

    tickers, meta = [], {}
    for item in raw_data:
        code = item['s'].split(':')[-1]
        yf_code = f"{code}.SS" if code.startswith('6') else f"{code}.SZ"
        tickers.append(yf_code)
        meta[yf_code] = {"ind": (item['d'][1] or "Misc")[:6], "mktcap": item['d'][2], "symbol": code}

    # 2. 同步数据
    all_data = yf.download(tickers, period="260d", group_by='ticker', progress=False, threads=True)
    
    # 3. 计算位阶
    stats = []
    valid_tickers = []
    for t in tickers:
        try:
            if t not in all_data or all_data[t].empty: continue
            df = all_data[t].dropna()
            if len(df) < 120: continue
            c = df['Close']
            ytd_price = c.loc[c.index >= START_DATE_REF].iloc[0] if any(c.index >= START_DATE_REF) else c.iloc[0]
            stats.append({
                "code": t, "r1": (c.iloc[-1]/c.iloc[-2])-1, "r5": (c.iloc[-1]/c.iloc[-5])-1,
                "r20": (c.iloc[-1]/c.iloc[-20])-1, "r60": (c.iloc[-1]/c.iloc[-60])-1,
                "r120": (c.iloc[-1]/c.iloc[-120])-1, "rytd": (c.iloc[-1]/ytd_price)-1
            })
            valid_tickers.append(t)
        except: continue
    
    full_df = pd.DataFrame(stats)
    for p in [5, 20, 60, 120]:
        full_df[f'REL{p}'] = full_df[f'r{p}'].rank(pct=True) * 99
    full_df['RankScore'] = (full_df['REL60']*0.4 + full_df['REL20']*0.4 + full_df['REL120']*0.2)

    # 4. 指标建模
    results = []
    for t in valid_tickers:
        try:
            df = all_data[t].dropna()
            c, v, h, l = df['Close'], df['Volume'], df['High'], df['Low']
            curr_p = float(c.iloc[-1])
            
            # --- 核心修改：离线生成 Sparkline 价格序列 ---
            # 获取最近 60 个价格点并转为逗号分隔字符串
            prices_60 = c.tail(60).round(2).tolist()
            prices_str = ",".join(map(str, prices_60))
            
            # 颜色逻辑：当前价 vs 60日前价
            line_color = "#00b050" if curr_p >= prices_60[0] else "#ff0000"
            
            # 生成公式：直接将价格填入大括号内 {p1, p2, p3...}
            trend_formula = f'=SPARKLINE({{{prices_str}}}, {{"charttype","line";"linewidth",2;"color","{line_color}"}})'
            
            # 其他指标
            ma20 = c.rolling(20).mean().iloc[-1]
            res = "3-Line" if curr_p > ma20 > c.rolling(50).mean().iloc[-1] > c.rolling(120).mean().iloc[-1] else "---"
            vol_ratio = v.iloc[-1] / v.iloc[-5:-1].mean() if v.iloc[-5:-1].mean() > 0 else 0
            row = full_df[full_df['code'] == t].iloc[0]
            
            results.append({
                "Ticker": meta[t]['symbol'], "Industry": meta[t]['ind'], "Score": int(row['RankScore'] + (10 if "3-Line" in res else 0)),
                "1D%": f"{row['r1']*100:+.2f}%", "近60日趨勢(圖)": trend_formula,
                "Action": "🎯Setup" if (c.iloc[-5:].std()/c.iloc[-5:].mean()*100 < 2 and vol_ratio < 1) else "Hold",
                "Resonance": res, "ADR": round(((h-l)/l).rolling(20).mean().iloc[-1]*100, 2),
                "Vol_Ratio": round(vol_ratio, 1), "Bias": f"{(curr_p-ma20)/ma20*100:+.1f}%",
                "MktCap": f"{meta[t]['mktcap']/1e8:.0f}Y", "Rank": int(row['RankScore']),
                "REL5": int(row['REL5']), "REL20": int(row['REL20']), "REL60": int(row['REL60']), "REL120": int(row['REL120']),
                "R20": round(curr_p/c.iloc[-20], 2), "R60": round(curr_p/c.iloc[-60], 2), "R120": round(curr_p/c.iloc[-120], 2),
                "Price": round(curr_p, 2), f"From {START_DATE_REF}": f"{row['rytd']*100:+.1f}%"
            })
        except: continue

    # 5. 写入
    sh = init_sheet()
    if sh and results:
        df_final = pd.DataFrame(results).sort_values("Score", ascending=False).head(80)
        if sh.col_count < 22: sh.add_cols(22 - sh.col_count)
        sh.clear()
        sh.update(range_name='A1', values=[df_final.columns.tolist()] + df_final.values.tolist(), value_input_option='USER_ENTERED')
        sh.update(range_name='V1', values=[[f"Updated: {update_str}"]])
        
        # 格式美化
        last_row = len(df_final) + 1
        requests_body = [
            {"updateDimensionProperties": {"range": {"sheetId": sh.id, "dimension": "ROWS", "startIndex": 1, "endIndex": last_row}, "properties": {"pixelSize": 42}, "fields": "pixelSize"}},
            {"updateDimensionProperties": {"range": {"sheetId": sh.id, "dimension": "COLUMNS", "startIndex": 4, "endIndex": 5}, "properties": {"pixelSize": 140}, "fields": "pixelSize"}},
            {"repeatCell": {"range": {"sheetId": sh.id, "startRowIndex": 0, "endRowIndex": last_row}, "cell": {"userEnteredFormat": {"verticalAlignment": "MIDDLE", "horizontalAlignment": "CENTER"}}, "fields": "userEnteredFormat(verticalAlignment,horizontalAlignment)"}}
        ]
        sh.spreadsheet.batch_update({"requests": requests_body})
        sh.format("A1:U1", {"textFormat": {"bold": True, "foregroundColor": {"red":1,"green":1,"blue":1}}, "backgroundColor": {"red":0.2,"green":0.2,"blue":0.2}})
        sh.freeze(rows=1)
        print(f"✅ V60.25 风格同步完成！图表已通过离线数据修复。")

if __name__ == "__main__":
    run_v60_pro()
