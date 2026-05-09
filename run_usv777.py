import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import time
import requests
import json
import warnings
import math
import random

warnings.filterwarnings('ignore')

# ==========================================
# 1. 系統配置中心
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"

# 排除黑名單 (已退市、幽靈數據)
GHOST_TICKERS = ["SNDK"]

MONOPOLY_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "TSM", "ASML", "AVGO",
    "V", "MA", "BRK-B", "SPGI", "MCO", "LLY", "NVO", "UNH", "JNJ", "ISRG",       
    "WMT", "COST", "PG", "KO", "PEP", "LIN", "SHW", "CAT", "DE", "LMT",         
    "UNP", "WM", "RSG", "NOW", "SNPS", "CDNS", "VRT", "PWR", "HWM", "CAVA"
]

FALLBACK_UNIVERSE = [t for t in MONOPOLY_TICKERS if t not in GHOST_TICKERS] + [
    "AMD", "CRWD", "PLTR", "PANW", "SNOW", "DDOG", "NET", "MDB", "TEAM", "WDAY",
    "ADBE", "CRM", "INTU", "QCOM", "TXN", "AMAT", "LRCX", "KLAC", "MU", "ARM"
]

EXCLUDED_INDUSTRIES = ['Banks', 'Insurance', 'Financial', 'Credit Services']
MAX_PER_SECTOR = 4  

# ==========================================
# 2. 核心工具函數
# ==========================================
def sync_to_google_sheet(sheet_name, matrix):
    try:
        payload = {"sheet_name": sheet_name, "data": matrix}
        requests.post(WEBAPP_URL, json=payload, timeout=30)
        print(f"🎉 同步成功 -> 分頁: [{sheet_name}]")
    except Exception as e: print(f"❌ 同步失敗: {e}")

def safe_get(info_dict, key, default=0):
    val = info_dict.get(key)
    try: return float(val) if val is not None else default
    except: return default

def extract_ticker_data(data, ticker):
    try:
        if isinstance(data.columns, pd.MultiIndex):
            if ticker in data.columns.levels[0]: return data[ticker].dropna()
            elif ticker in data.columns.levels[1]: return data.xs(ticker, level=1, axis=1).dropna()
        return data.dropna()
    except: return pd.DataFrame()

def calculate_return(series, p):
    try:
        if len(series) > p: return (float(series.iloc[-1]) / float(series.iloc[-(p+1)]) - 1) * 100
    except: pass
    return 0

# ==========================================
# 3. 策略 B: 右側 RPS 動能全景 (V13.1 修復對齊版)
# ==========================================
def run_right_side_momentum():
    print("\n" + "="*50 + "\n🚀 [策略 B: RPS 動能全景 V13.1] 啟動...")
    
    try:
        tables = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        tickers = [t.replace('.', '-') for t in tables[0]['Symbol'].tolist()]
        tickers = [t for t in tickers if t not in GHOST_TICKERS] # 移除黑名單
    except: tickers = FALLBACK_UNIVERSE
    if "SPY" not in tickers: tickers.append("SPY")

    print(f"📡 掃描 {len(tickers)} 隻標的數據...")
    data = yf.download(tickers, period="2y", interval="1d", group_by='ticker', auto_adjust=True, progress=False)
    spy_close = extract_ticker_data(data, "SPY")['Close']

    # --- 第一階段：RPS 計算 ---
    stats = []
    for t in tickers:
        df = extract_ticker_data(data, t)
        if df.empty or len(df) < 252 or df['Volume'].iloc[-1] < 1000: continue
        stats.append({
            "T": t, "df": df,
            "r20": calculate_return(df['Close'], 20),
            "r60": calculate_return(df['Close'], 60),
            "r120": calculate_return(df['Close'], 120)
        })
    
    df_stats = pd.DataFrame(stats)
    df_stats['20R'] = df_stats['r20'].rank(pct=True) * 100
    df_stats['60R'] = df_stats['r60'].rank(pct=True) * 100
    df_stats['120R'] = df_stats['r120'].rank(pct=True) * 100
    df_stats['RPS'] = (df_stats['20R'] * 0.2) + (df_stats['60R'] * 0.4) + (df_stats['120R'] * 0.4)

    # --- 第二階段：篩選 ---
    cands = []
    for _, row in df_stats.iterrows():
        if row['T'] == "SPY": continue
        df = row['df']
        curr_p, ma50 = float(df['Close'].iloc[-1]), df['Close'].tail(50).mean()
        if row['RPS'] < 70 or curr_p < ma50: continue

        cands.append({
            "T": row['T'], "P": curr_p, "RPS": row['RPS'], "20R": row['20R'], "60R": row['60R'], "120R": row['120R'],
            "1D": calculate_return(df['Close'], 1), "Bias": ((curr_p - ma50)/ma50)*100,
            "ADR": ((df['High'] - df['Low']) / df['Low']).tail(20).mean() * 100,
            "Tight": float((df['Close'].tail(15).std() / df['Close'].tail(15).mean()) * 100),
            "TrendPlot": f'=SPARKLINE({{{",".join([str(round(p,2)) for p in df["Close"].tail(60).tolist()])}}}, {{"charttype","line";"color","#2E86C1"}})'
        })

    print(f"🔬 進入基本面體檢與因子共振 (共 {len(cands)} 隻)...")
    final = []
    for c in sorted(cands, key=lambda x: x['RPS'], reverse=True)[:45]:
        try:
            time.sleep(0.1)
            info = yf.Ticker(c['T']).info
            sec = str(info.get('sector', 'Unknown'))
            if any(ex.lower() in sec.lower() for ex in EXCLUDED_INDUSTRIES): continue
            
            rev_g = safe_get(info, 'revenueGrowth') * 100
            op_m = safe_get(info, 'operatingMargins') * 100
            total_rev = safe_get(info, 'totalRevenue', 1) or 1
            is_tech = 'Technology' in sec or 'Software' in str(info.get('industry', ''))
            fin_score = (rev_g + (safe_get(info, 'freeCashflow')/total_rev)*100) if is_tech else (op_m + rev_g)
            
            if fin_score > 5:
                c['Sec'] = sec[:12]
                tags = f"{'R40' if is_tech else '利潤'}({fin_score:.0f}%)"
                if c['Tight'] < 3.5: tags += " 💎收斂"
                c['Pos'] = f"{min(3.0 / c['ADR'] * 10, 15):.0f}%"
                c['Msg'] = tags
                c['Tot'] = (c['RPS'] * 0.7) + (min(fin_score, 100) * 0.3) - (abs(c['Bias']-5)*0.5) - (c['Tight']*2)
                final.append(c)
        except: continue

    # 板塊熔斷與排序
    top20, sector_counts = [], {}
    for r in sorted(final, key=lambda x: x['Tot'], reverse=True):
        if sector_counts.get(r['Sec'], 0) < MAX_PER_SECTOR:
            top20.append(r)
            sector_counts[r['Sec']] = sector_counts.get(r['Sec'], 0) + 1
        if len(top20) >= 20: break

    # --- 4. 終極 16 欄位對齊矩陣 ---
    header = [["🚀 RPS 動能全景 V13.1", "更新:", datetime.datetime.now().strftime('%m-%d %H:%M'), "Ghost:", "SNDK Cleaned", "", "", "", "", "", "", "", "", "", "", ""],
              ["排名", "代碼", "板塊", "現價", "1D%", "ADR", "Bias", "60日趨勢", "20R", "60R", "120R", "RPS總分", "基本面標籤", "建議倉位", "綜合得分", "實戰指令"]]
    
    final_list = []
    if not top20:
        final_list.append(["-", "市場冷淡，暫無強勢股", "-"] + ["-"]*13)
    else:
        for i, r in enumerate(top20):
            if r['Bias'] > 25: action = "🚫 絕不追高"
            elif r['Bias'] > 15: action = "⏳ 等待回調"
            elif r['Bias'] < 6 and r['Tight'] < 3.5: action = "🎯 破點狙擊"
            else: action = "觀察 20EMA"
            
            final_list.append([
                f"T{i+1}", r['T'], r['Sec'], round(r['P'], 2), f"{r['1D']:.1f}%", f"{r['ADR']:.1f}%", f"{r['Bias']:.1f}%", 
                r['TrendPlot'], f"{int(r['20R'])}", f"{int(r['60R'])}", f"{int(r['120R'])}", 
                f"{r['RPS']:.1f}", r['Msg'], r['Pos'], f"{r['Tot']:.1f}", action
            ])
    
    sync_to_google_sheet("🚀右側_動能成長", header + final_list)

if __name__ == "__main__":
    run_right_side_momentum()
