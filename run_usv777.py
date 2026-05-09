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

MONOPOLY_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "TSM", "ASML", "AVGO",
    "LLY", "NVO", "UNH", "JNJ", "ISRG", "VRT", "PWR", "HWM", "CAVA", "CVNA", "ROKU", 
    "PLTR", "GEV", "MU", "SNPS", "LITE", "TER", "CAT", "LIN", "EOG", "ALB", "WM", "SNDK"
]

FALLBACK_UNIVERSE = MONOPOLY_TICKERS + [
    "AMD", "CRWD", "PANW", "SNOW", "DDOG", "NET", "MDB", "TEAM", "WDAY",
    "ADBE", "CRM", "INTU", "QCOM", "TXN", "AMAT", "LRCX", "KLAC", "ARM",
    "JPM", "GS", "WMT", "COST", "SLB", "GE", "RTX", "BA", "HON", "UPS"
]

EXCLUDED_INDUSTRIES = ['Banks', 'Insurance']
MAX_PER_SECTOR = 4  # 保持板塊多樣性

# ==========================================
# 2. 核心計算裝甲
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
    if len(series) > p: return (float(series.iloc[-1]) / float(series.iloc[-(p+1)]) - 1) * 100
    return 0

# ==========================================
# 3. 🌍 市場環境與建議總倉位 (Regime Filter)
# ==========================================
def get_market_regime():
    try:
        spy = yf.download("SPY", period="6mo", progress=False)['Close']
        vix = yf.download("^VIX", period="5d", progress=False)['Close'].iloc[-1]
        vix = float(vix)
        is_bull = float(spy.iloc[-1]) > float(spy.tail(50).mean())
        
        # 根據 VIX 動態建議總倉位
        if vix < 15: pos_msg = "🔥 極度看多 (100% 倉位)"
        elif vix < 20: pos_msg = "☀️ 穩定進攻 (70% 倉位)"
        elif vix < 25: pos_msg = "⛅ 謹慎狙擊 (40% 倉位)"
        else: pos_msg = "⛈️ 避險防守 (10% 倉位)"
        
        return is_bull, vix, pos_msg
    except: return True, 18.0, "數據讀取失敗"

# ==========================================
# 4. 🚀 策略核心: V80 宗師狙擊引擎
# ==========================================
def run_v80_sniper_system():
    print("\n" + "="*50 + "\n🚀 [V80 Pro Sniper 宗師狙擊系統] 啟動...")
    is_bull, vix, pos_msg = get_market_regime()
    
    try:
        tables = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        tickers = list(set([t.replace('.', '-') for t in tables[0]['Symbol'].tolist()] + FALLBACK_UNIVERSE))
    except: tickers = FALLBACK_UNIVERSE
    if "SPY" not in tickers: tickers.append("SPY")

    print(f"📡 掃描全美 {len(tickers)} 隻核心標的...")
    data = yf.download(tickers, period="2y", interval="1d", group_by='ticker', auto_adjust=True, progress=False)
    spy_close = extract_ticker_data(data, "SPY")['Close']

    # --- 第一階段: RPS & 基礎因子 ---
    stats = []
    for t in tickers:
        df = extract_ticker_data(data, t)
        if df.empty or len(df) < 252: continue
        close = df['Close']
        stats.append({
            "T": t, "df": df,
            "r20": calculate_return(close, 20),
            "r60": calculate_return(close, 60),
            "r120": calculate_return(close, 120),
            "close": close, "vol": df['Volume']
        })
    
    df_stats = pd.DataFrame(stats)
    df_stats['20R'] = df_stats['r20'].rank(pct=True) * 100
    df_stats['60R'] = df_stats['r60'].rank(pct=True) * 100
    df_stats['120R'] = df_stats['r120'].rank(pct=True) * 100
    df_stats['RPS'] = (df_stats['20R'] * 0.2) + (df_stats['60R'] * 0.4) + (df_stats['120R'] * 0.4)

    # --- 第二階段: 狼群共振預處理 ---
    candidates = []
    for _, row in df_stats.iterrows():
        if row['T'] == "SPY": continue
        df, t = row['df'], row['T']
        close = row['close']
        curr_p, ma50 = float(close.iloc[-1]), close.tail(50).mean()
        ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
        
        # 門檻：RPS > 80 (大師位)
        if row['RPS'] < 80 or curr_p < ma50: continue

        candidates.append({
            "T": t, "P": curr_p, "RPS": row['RPS'], "EMA20": ema20,
            "1D": calculate_return(close, 1), "Bias": ((curr_p - ma50)/ma50)*100,
            "ADR": ((df['High'] - df['Low']) / df['Low']).tail(20).mean() * 100,
            "RVOL": float(row['vol'].iloc[-1] / row['vol'].tail(10).mean()),
            "Tight": float((close.tail(15).std() / close.tail(15).mean()) * 100),
            "Risk": ((curr_p - ma50) / curr_p) * 100,
            "TrendPlot": f'=SPARKLINE({{{",".join([str(round(p,2)) for p in close.tail(60).tolist()])}}}, {{"charttype","line";"color","#2E86C1"}})'
        })

    # --- 第三階段: 基本面體檢與共振計算 ---
    print(f"🔬 進入因子共振體檢 (共 {len(candidates)} 隻)...")
    final_pool = []
    temp_sector_map = {}
    
    for c in sorted(candidates, key=lambda x: x['RPS'], reverse=True)[:50]:
        try:
            time.sleep(0.1)
            info = yf.Ticker(c['T']).info
            sec = str(info.get('sector', 'Unknown'))
            if any(ex.lower() in sec.lower() for ex in EXCLUDED_INDUSTRIES): continue
            
            rev_g = safe_get(info, 'revenueGrowth') * 100
            fcf = safe_get(info, 'freeCashflow')
            total_rev = safe_get(info, 'totalRevenue', 1) or 1
            op_m = safe_get(info, 'operatingMargins') * 100
            
            is_tech = 'Technology' in sec or 'Software' in str(info.get('industry', ''))
            fin_score = (rev_g + (fcf/total_rev)*100) if is_tech else (op_m + rev_g)
            
            if fin_score > 10:
                c['Sec'] = sec[:12]
                c['Fin_S'] = fin_score
                c['Pos'] = f"{min(3.0 / max(c['ADR'], 1.0) * 10, 15):.0f}%"
                c['Msg'] = f"{'R40' if is_tech else '利潤'}({fin_score:.0f}%)" + (f" 💎" if c['Tight']<3.5 else "") + (f" 📈" if c['RVOL']>1.8 else "")
                
                # 記錄板塊出現次數用於「狼群共振」加分
                temp_sector_map[c['Sec']] = temp_sector_map.get(c['Sec'], 0) + 1
                final_pool.append(c)
        except: continue

    # --- 第四階段: 宗師級指令分配 ---
    final_list = []
    # 按照綜合得分排序：RPS + 基本面 - 乖離扣分
    for r in final_pool:
        r['Resonance_Count'] = temp_sector_map.get(r['Sec'], 0)
        # 宗師總分公式：RPS(60%) + 基本面(20%) + 狼群共振(10%) - 乖離(10%)
        r['Final_Score'] = (r['RPS'] * 0.6) + (min(r['Fin_S'], 100) * 0.2) + (r['Resonance_Count'] * 5) - (abs(r['Bias']-5) * 0.5)

    sorted_final = sorted(final_pool, key=lambda x: x['Final_Score'], reverse=True)
    top20, counts = [], {}
    
    for r in sorted_final:
        if counts.get(r['Sec'], 0) < MAX_PER_SECTOR:
            # 判斷買點距離 (Sniper Countdown)
            dist_to_ema = (r['P'] - r['EMA20']) / r['P'] * 100
            
            if r['Bias'] > 25: action = "🚫 絕不追高"
            elif r['Bias'] > 15: action = f"⏳ 觀察 (距買點{dist_to_ema:.1f}%)"
            elif abs(dist_to_ema) < 1.5: action = f"🔥 狙擊開火! (風險-{r['Risk']:.1f}%)"
            elif r['Bias'] < 8: action = f"🎯 潛伏買入 (風險-{r['Risk']:.1f}%)"
            else: action = "等待回踩"
            
            # 增加狼群共振標籤
            t_display = ("🐺" if r['Resonance_Count'] >= 3 else "") + r['T']
            
            top20.append([
                f"T{len(top20)+1}", t_display, r['Sec'], round(r['P'], 2), f"{r['1D']:.1f}%", f"{r['ADR']:.1f}%",
                f"{r['Bias']:.1f}%", r['TrendPlot'], f"{r['RPS']:.1f}", r['Msg'], r['Pos'], f"{r['Final_Score']:.1f}", action
            ])
            counts[r['Sec']] = counts.get(r['Sec'], 0) + 1
        if len(top20) >= 20: break

    # --- 第五階段: 雲端同步 ---
    header = [
        ["🏰 V80 Pro Sniper 宗師矩陣", "更新:", datetime.datetime.now().strftime('%m-%d %H:%M'), "建議倉位:", pos_msg, "VIX:", f"{vix:.1f}", "", "", "", "", "", ""],
        ["排名", "代碼", "板塊", "現價", "1D%", "ADR", "50MA乖離", "60日趨勢", "RPS總分", "基本面標籤", "建議頭寸", "綜合得分", "實戰指令(風控)"]
    ]
    sync_to_google_sheet("🚀右側_動能成長", header + top20)

if __name__ == "__main__":
    run_v80_sniper_system()
