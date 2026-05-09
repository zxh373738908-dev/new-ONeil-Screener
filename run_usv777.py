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

# 核心種子池
MONOPOLY_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "TSM", "ASML", "AVGO",
    "LLY", "NVO", "UNH", "JNJ", "ISRG", "VRT", "PWR", "HWM", "CAVA", "CVNA", "ROKU", 
    "PLTR", "GEV", "MU", "SNPS", "LITE", "TER", "CAT", "LIN", "EOG", "ALB", "WM"
]

FALLBACK_UNIVERSE = MONOPOLY_TICKERS + [
    "AMD", "CRWD", "PANW", "SNOW", "DDOG", "NET", "MDB", "TEAM", "WDAY",
    "ADBE", "CRM", "INTU", "QCOM", "TXN", "AMAT", "LRCX", "KLAC", "ARM",
    "JPM", "GS", "WMT", "COST", "SLB", "GE", "RTX", "BA", "HON", "UPS"
]

EXCLUDED_INDUSTRIES = ['Banks', 'Insurance']
MAX_PER_SECTOR = 3  

# ==========================================
# 2. 核心計算裝甲
# ==========================================
def sync_to_google_sheet(sheet_name, matrix):
    try:
        def safe_json_val(val):
            if isinstance(val, float) and not math.isfinite(val): return 0
            return str(val)
        payload = {"sheet_name": sheet_name, "data": json.loads(json.dumps(matrix, default=safe_json_val))}
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
    try:
        if len(series) > p: return (float(series.iloc[-1]) / float(series.iloc[-(p+1)]) - 1) * 100
    except: pass
    return 0

# ==========================================
# 3. 🚀 主引擎: V80.7 宗師「深潛」版
# ==========================================
def run_right_side_momentum():
    print("\n" + "="*50 + "\n🚀 [策略 B: V80.7 宗師全美深潛版] 啟動...")
    
    try:
        vix_raw = yf.download("^VIX", period="5d", progress=False)['Close'].iloc[-1]
        vix = float(vix_raw)
        # 【優化】強制抓取全美 500 強，確保不漏掉任何一個「低風險啟動」標的
        tables = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        tickers = list(set([t.replace('.', '-') for t in tables[0]['Symbol'].tolist()] + FALLBACK_UNIVERSE))
    except: tickers = FALLBACK_UNIVERSE; vix = 18.0

    print(f"📡 正在掃描全美 {len(tickers)} 隻戰士...")
    data = yf.download(tickers, period="2y", interval="1d", group_by='ticker', auto_adjust=True, progress=False)
    
    stats_list = []
    for t in tickers:
        df = extract_ticker_data(data, t)
        if df.empty or len(df) < 200: continue
        close = df['Close']
        stats_list.append({
            "T": t, "df": df, "close": close, "vol": df['Volume'],
            "r20": calculate_return(close, 20), "r60": calculate_return(close, 60),
            "r120": calculate_return(close, 120), "r250": calculate_return(close, 250)
        })
    
    df_stats = pd.DataFrame(stats_list)
    df_stats['20R'] = df_stats['r20'].rank(pct=True) * 100
    df_stats['60R'] = df_stats['r60'].rank(pct=True) * 100
    df_stats['120R'] = df_stats['r120'].rank(pct=True) * 100
    df_stats['RPS'] = (df_stats['20R'] * 0.2) + (df_stats['60R'] * 0.4) + (df_stats['120R'] * 0.4)

    # 初篩：RPS > 75 (動能基因)
    raw_cands = []
    for _, row in df_stats.iterrows():
        df, close = row['df'], row['close']
        curr_p, ma50 = float(close.iloc[-1]), close.tail(50).mean()
        ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
        
        if row['RPS'] < 75 or curr_p < ma50: continue

        raw_cands.append({
            "T": row['T'], "P": curr_p, "RPS": row['RPS'], "EMA20": ema20,
            "1D": calculate_return(close, 1), "Bias": ((curr_p - ma50)/ma50)*100,
            "ADR": ((df['High']-df['Low'])/df['Low']).tail(20).mean()*100,
            "RVOL": float(row['vol'].iloc[-1] / max(row['vol'].tail(10).mean(), 1)),
            "Tight": float((close.tail(15).std() / close.tail(15).mean()) * 100),
            "Risk": ((curr_p - ma50) / curr_p) * 100,
            "Trend": f'=SPARKLINE({{{",".join([str(round(p,2)) for p in close.tail(60).tolist()])}}}, {{"charttype","line";"color","#2E86C1"}})'
        })

    print(f"🔬 執行大師級因子共振測算 (共 {len(raw_cands)} 隻)...")
    final_pool, sector_map = [], {}
    processed = set()

    for c in sorted(raw_cands, key=lambda x: x['RPS'], reverse=True)[:65]:
        if c['T'] in processed: continue
        try:
            time.sleep(0.01)
            info = yf.Ticker(c['T']).info
            sec = str(info.get('sector', 'Unknown'))
            if any(ex.lower() in sec.lower() for ex in EXCLUDED_INDUSTRIES): continue
            
            rev_g = safe_get(info, 'revenueGrowth') * 100
            total_rev = safe_get(info, 'totalRevenue', 1) or 1
            op_m = safe_get(info, 'operatingMargins') * 100
            
            is_tech = 'Technology' in sec or 'Software' in str(info.get('industry', ''))
            fin_score = (rev_g + 10) if is_tech else (op_m + rev_g)
            
            if fin_score > 5:
                c['Sec'], c['Fin_S'] = sec[:10], fin_score
                c['Msg'] = f"{'R40' if is_tech else '利潤'}({fin_score:.0f}%)" + (f" 💎" if c['Tight']<3.5 else "")
                sector_map[c['Sec']] = sector_map.get(c['Sec'], 0) + 1
                
                # --- 「先勝後戰」宗師評分 V80.7 ---
                dist = abs(c['P'] - c['EMA20']) / c['P'] * 100
                # 核心分
                score = (c['RPS'] * 0.5) + (min(fin_score, 100) * 0.2)
                # 買點權重 (最重要的加減分)
                if dist < 1.5: score += 40             # 狙擊位大加分
                if c['Bias'] > 20: score -= (c['Bias'] - 20) * 8 # 超買極速扣分
                if c['Tight'] < 3.0: score += 15       # 收斂加分
                
                c['Score'], c['Dist'] = score, dist
                final_pool.append(c); processed.add(c['T'])
        except: continue

    sorted_final = sorted(final_pool, key=lambda x: x['Score'], reverse=True)
    top10, sector_counts = [], {}
    
    for r in sorted_final:
        if sector_counts.get(r['Sec'], 0) < MAX_PER_SECTOR:
            if r['Bias'] > 25: action = "🚫 絕不追高"
            elif r['Score'] > 85 and r['Dist'] < 1.8: action = "🔥 狙擊開火!"
            elif r['Bias'] < 8: action = "🎯 底部潛伏"
            else: action = f"觀察(距買點{r['Dist']:.1f}%)"
            
            t_display = ("🐺" if sector_map.get(r['Sec'], 0) >= 3 else "") + r['T']
            top10.append([
                f"T{len(top10)+1}", t_display, r['Sec'], round(r['P'], 2), f"{r['1D']:.1f}%", f"{r['ADR']:.1f}%",
                f"{r['Bias']:.1f}%", r['Trend'], f"{r['RPS']:.1f}", r['Msg'], f"{r['Score']:.1f}", action
            ])
            sector_counts[r['Sec']] = sector_counts.get(r['Sec'], 0) + 1
        if len(top10) >= 10: break

    header = [
        ["🏰 V80.7 Master Sniper 全美深潛版", "更新:", datetime.datetime.now().strftime('%m-%d %H:%M'), "VIX:", f"{vix:.1f}", "戰略:", "先勝後戰", "", "", "", "", ""],
        ["排名", "代碼", "板塊", "現價", "1D%", "ADR", "50MA乖離", "60日趨勢", "RPS總分", "基本面", "評分", "作戰指令"]
    ]
    sync_to_google_sheet("🚀右側_動能成長", header + top10)

if __name__ == "__main__":
    run_right_side_momentum()
