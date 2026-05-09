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
# 1. 配置中心
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"

# 納入大師持倉與全美強勢股池 (包含 SNDK)
MONOPOLY_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "TSM", "ASML", "AVGO",
    "LLY", "NVO", "UNH", "JNJ", "ISRG", "VRT", "PWR", "HWM", "CAVA", "CVNA", "ROKU", 
    "PLTR", "GEV", "MU", "SNPS", "LITE", "TER", "CAT", "LIN", "EOG", "ALB", "WM", "SNDK"
]

FALLBACK_UNIVERSE = MONOPOLY_TICKERS + [
    "AMD", "CRWD", "PANW", "SNOW", "DDOG", "NET", "MDB", "TEAM", "WDAY",
    "ADBE", "CRM", "INTU", "QCOM", "TXN", "AMAT", "LRCX", "KLAC", "ARM",
    "JPM", "GS", "WMT", "COST", "SLB", "GE", "RTX", "BA", "HON", "UPS", "PWR"
]

EXCLUDED_INDUSTRIES = ['Banks', 'Insurance']
MAX_PER_SECTOR = 3  

# ==========================================
# 2. 核心計算引擎
# ==========================================
def sync_to_google_sheet(sheet_name, matrix):
    try:
        payload = {"sheet_name": sheet_name, "data": matrix}
        requests.post(WEBAPP_URL, json=payload, timeout=30)
        print(f"🎉 同步成功 -> [{sheet_name}]")
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
    if len(series) > p: return (float(series.iloc[-1]) / float(series.iloc[-(p+1)]) - 1) * 100
    return 0

def get_market_regime():
    try:
        spy = yf.download("SPY", period="6mo", progress=False)['Close']
        vix = yf.download("^VIX", period="5d", progress=False)['Close'].iloc[-1]
        is_bull = float(spy.iloc[-1]) > float(spy.tail(50).mean())
        if vix < 18: msg = "🔥 極度看多"
        elif vix < 22: msg = "☀️ 進攻型氣候"
        else: msg = "⛈️ 避險型氣候"
        return is_bull, float(vix), msg
    except: return True, 18.0, "環境穩定"

# ==========================================
# 3. 🚀 核心策略: V80.2 大師經驗矩陣
# ==========================================
def run_right_side_momentum():
    print("\n" + "="*50 + "\n🚀 [策略 B: V80.2 大師經驗矩陣版] 啟動...")
    is_bull, vix, env_msg = get_market_regime()
    
    try:
        tables = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        tickers = list(set([t.replace('.', '-') for t in tables[0]['Symbol'].tolist()] + FALLBACK_UNIVERSE))
    except: tickers = FALLBACK_UNIVERSE
    if "SPY" not in tickers: tickers.append("SPY")

    print(f"📡 掃描全美 {len(tickers)} 隻標的...")
    data = yf.download(tickers, period="2y", interval="1d", group_by='ticker', auto_adjust=True, progress=False)
    spy_close = extract_ticker_data(data, "SPY")['Close']

    stats = []
    for t in tickers:
        df = extract_ticker_data(data, t)
        if df.empty or len(df) < 200: continue
        close = df['Close']
        stats.append({
            "T": t, "df": df, "close": close, "vol": df['Volume'],
            "r20": calculate_return(close, 20),
            "r60": calculate_return(close, 60),
            "r120": calculate_return(close, 120),
            "r250": calculate_return(close, 250)
        })
    
    df_stats = pd.DataFrame(stats)
    df_stats['20R'] = df_stats['r20'].rank(pct=True) * 100
    df_stats['60R'] = df_stats['r60'].rank(pct=True) * 100
    df_stats['120R'] = df_stats['r120'].rank(pct=True) * 100
    df_stats['RPS'] = (df_stats['20R'] * 0.2) + (df_stats['60R'] * 0.4) + (df_stats['120R'] * 0.4)

    # 第一次過濾：大師 RPS 門檻
    raw_cands = []
    for _, row in df_stats.iterrows():
        if row['T'] == "SPY": continue
        df, t, close = row['df'], row['T'], row['close']
        curr_p, ma50 = float(close.iloc[-1]), close.tail(50).mean()
        ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
        
        if row['RPS'] < 80 or curr_p < ma50: continue

        raw_cands.append({
            "T": t, "P": curr_p, "RPS": row['RPS'], "EMA20": ema20,
            "1D": calculate_return(close, 1), "Bias": ((curr_p - ma50)/ma50)*100,
            "ADR": ((df['High'] - df['Low']) / df['Low']).tail(20).mean() * 100,
            "RVOL": float(row['vol'].iloc[-1] / max(row['vol'].tail(10).mean(), 1)),
            "Tight": float((close.tail(15).std() / close.tail(15).mean()) * 100),
            "Risk": ((curr_p - ma50) / curr_p) * 100,
            "TrendPlot": f'=SPARKLINE({{{",".join([str(round(p,2)) for p in close.tail(60).tolist()])}}}, {{"charttype","line";"color","#2E86C1"}})'
        })

    print(f"🔬 執行大師經驗算法與板塊對齊...")
    final_pool, sector_map = [], {}
    for c in raw_cands:
        try:
            time.sleep(0.05)
            info = yf.Ticker(c['T']).info
            sec = str(info.get('sector', 'Unknown'))
            if any(ex.lower() in sec.lower() for ex in EXCLUDED_INDUSTRIES): continue
            
            rev_g = safe_get(info, 'revenueGrowth') * 100
            total_rev = safe_get(info, 'totalRevenue', 1) or 1
            fcf = safe_get(info, 'freeCashflow')
            op_m = safe_get(info, 'operatingMargins') * 100
            
            # 判斷是否為轉機股或高成長科技股
            is_tech = 'Technology' in sec or 'Software' in str(info.get('industry', ''))
            r40 = rev_g + (fcf/total_rev)*100
            fin_score = r40 if is_tech else (op_m + rev_g)
            
            if fin_score > 10 or c['T'] == "SNDK":
                c['Sec'], c['Fin_S'] = sec[:10], fin_score
                c['Msg'] = f"{'R40' if is_tech else '利潤'}({fin_score:.0f}%)" + (f" 💎" if c['Tight']<3.5 else "")
                sector_map[c['Sec']] = sector_map.get(c['Sec'], 0) + 1
                final_pool.append(c)
        except: continue

    # --- 【核心優化】大師級權重排序 ---
    for r in final_pool:
        res = sector_map.get(r['Sec'], 0)
        dist_to_ema20 = abs(r['P'] - r['EMA20']) / r['P'] * 100
        
        # 基礎分：RPS + 基本面 + 板塊共振
        score = (r['RPS'] * 0.5) + (min(r['Fin_S'], 100) * 0.2) + (res * 5)
        
        # 加減分邏輯：
        if dist_to_ema20 < 1.5: score += 20    # 狙擊位加分 (回踩到位)
        if r['Bias'] > 25: score -= 40         # 極度超買大扣分 (防追高)
        if r['Tight'] < 3.0: score += 10       # VCP 收斂加分
        if r['RVOL'] > 1.8: score += 10        # 機構放量加分
        
        r['Master_Score'] = score

    sorted_final = sorted(final_pool, key=lambda x: x['Master_Score'], reverse=True)
    top10, sector_counts = [], {}
    
    for r in sorted_final:
        if sector_counts.get(r['Sec'], 0) < MAX_PER_SECTOR:
            dist = (r['P'] - r['EMA20']) / r['P'] * 100
            if r['Bias'] > 25: action = "🚫 絕不追高"
            elif dist < 1.5 and r['Tight'] < 4: action = "🔥 狙擊開火"
            elif dist < 5: action = "🎯 破點狙擊"
            else: action = f"等回調({dist:.1f}%)"
            
            t_display = ("🐺" if sector_map.get(r['Sec'],0) >= 3 else "") + r['T']
            top10.append([
                f"T{len(top10)+1}", t_display, r['Sec'], round(r['P'], 2), f"{r['1D']:.1f}%", f"{r['ADR']:.1f}%",
                f"{r['Bias']:.1f}%", r['TrendPlot'], f"{r['RPS']:.1f}", r['Msg'], f"{r['Master_Score']:.1f}", action
            ])
            sector_counts[r['Sec']] = sector_counts.get(r['Sec'], 0) + 1
        if len(top10) >= 10: break

    header = [
        ["🏰 V80.2 Master Sniper 宗師矩陣", "更新:", datetime.datetime.now().strftime('%m-%d %H:%M'), "大盤:", env_msg, "VIX:", f"{vix:.1f}", "", "", "", "", ""],
        ["排名", "代碼", "板塊", "現價", "1D%", "ADR", "50MA乖離", "60日趨勢", "RPS總分", "基本面標籤", "大師評分", "實戰指令"]
    ]
    sync_to_google_sheet("🚀右側_動能成長", header + top10)

if __name__ == "__main__":
    run_right_side_momentum()
