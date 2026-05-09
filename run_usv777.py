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

# 核心戰場：只選最硬的龍頭與大師同步標的
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
MAX_PER_SECTOR = 3  

# ==========================================
# 2. 核心計算裝甲 (精確對齊 14 欄位)
# ==========================================
def sync_to_google_sheet(sheet_name, matrix):
    try:
        # 強制清理 NaN 與對齊欄位
        clean_matrix = []
        for row in matrix:
            clean_row = [str(x) if not isinstance(x, (int, float)) else (0 if math.isnan(x) else x) for x in row]
            clean_matrix.append(clean_row)
        
        payload = {"sheet_name": sheet_name, "data": clean_matrix}
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

# ==========================================
# 3. 🚀 主引擎: V80.5 「先勝後戰」矩陣
# ==========================================
def run_right_side_momentum():
    print("\n" + "="*50 + "\n🚀 [策略 B: V80.5 先勝後戰版] 啟動...")
    
    try:
        spy_df = yf.download("SPY", period="6mo", progress=False)
        vix = float(yf.download("^VIX", period="5d", progress=False)['Close'].iloc[-1])
        # 自動獲取標普名單以擴大獵殺範圍
        tables = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        tickers = list(set([t.replace('.', '-') for t in tables[0]['Symbol'].tolist()] + FALLBACK_UNIVERSE))
    except: 
        tickers = FALLBACK_UNIVERSE; vix = 18.0

    print(f"📡 掃描全美 {len(tickers)} 隻標的價格...")
    data = yf.download(tickers, period="2y", interval="1d", group_by='ticker', auto_adjust=True, progress=False)
    
    stats_list = []
    for t in tickers:
        df = extract_ticker_data(data, t)
        if df.empty or len(df) < 200: continue
        close = df['Close']
        stats_list.append({
            "T": t, "df": df, "close": close,
            "r20": calculate_return(close, 20), "r60": calculate_return(close, 60),
            "r120": calculate_return(close, 120)
        })
    
    df_stats = pd.DataFrame(stats_list)
    for col in ['20R', '60R', '120R']:
        df_stats[col] = df_stats[col.replace('R','r')].rank(pct=True) * 100
    df_stats['RPS'] = (df_stats['20R'] * 0.2) + (df_stats['60R'] * 0.4) + (df_stats['120R'] * 0.4)

    print(f"🔬 執行基本面體檢與安全邊際測算...")
    final_pool, sector_map = [], {}
    processed = set()

    for _, row in df_stats.sort_values('RPS', ascending=False).iterrows():
        t = row['T']
        if t in processed: continue
        try:
            df, close = row['df'], row['close']
            curr_p, ma50 = float(close.iloc[-1]), close.tail(50).mean()
            ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
            
            # 門檻：RPS > 80 (市場領導者) 且 價格回歸至 50MA 之上
            if row['RPS'] < 80 or curr_p < ma50: continue

            time.sleep(0.01)
            info = yf.Ticker(t).info
            sec = str(info.get('sector', 'Unknown'))
            if any(ex.lower() in sec.lower() for ex in EXCLUDED_INDUSTRIES): continue
            
            # 獲取硬核基本面
            rev_g = safe_get(info, 'revenueGrowth') * 100
            fcf = safe_get(info, 'freeCashflow')
            total_rev = safe_get(info, 'totalRevenue', 1) or 1
            op_m = safe_get(info, 'operatingMargins') * 100
            
            is_tech = 'Technology' in sec or 'Software' in str(info.get('industry', ''))
            r40 = rev_g + (fcf/total_rev)*100
            fin_score = r40 if is_tech else (op_m + rev_g)
            
            # 先勝原則：剔除基本面數據為負的標的（SNDK 除外，因為其數據特殊）
            if fin_score > 5 or t == "SNDK":
                tight = float((close.tail(15).std() / close.tail(15).mean()) * 100)
                bias = ((curr_p - ma50)/ma50)*100
                dist_to_ema = abs(curr_p - ema20) / curr_p * 100
                
                # --- 「先勝後戰」大師評分邏輯 ---
                # 基礎分
                m_score = (row['RPS'] * 0.4) + (min(fin_score, 100) * 0.2)
                
                # 安全性權重 (Bias Hammer)
                if bias > 20: m_score -= (bias - 20) * 5  # 每超買 1% 扣 5 分
                if bias < 6: m_score += 20               # 底部支撐加分
                
                # 緊緻度權重 (VCP Launchpad)
                if tight < 3.0: m_score += 15
                
                # 狙擊權重 (Entry Window)
                if dist_to_ema < 1.5: m_score += 25
                
                res = {
                    "T": t, "P": curr_p, "Sec": sec[:10], "RPS": row['RPS'], "Fin": fin_score,
                    "Bias": bias, "Tight": tight, "Dist": dist_to_ema, "Score": m_score,
                    "1D": calculate_return(close, 1), "ADR": ((df['High']-df['Low'])/df['Low']).tail(20).mean()*100,
                    "Trend": f'=SPARKLINE({{{",".join([str(round(p,2)) for p in close.tail(60).tolist()])}}}, {{"charttype","line";"color","#2E86C1"}})'
                }
                final_pool.append(res)
                processed.add(t)
                sector_map[res['Sec']] = sector_map.get(res['Sec'], 0) + 1
        except: continue

    # 最終排序與板塊熔斷
    sorted_final = sorted(final_pool, key=lambda x: x['Score'], reverse=True)
    top10, counts = [], {}
    
    for r in sorted_final:
        if counts.get(r['Sec'], 0) < MAX_PER_SECTOR:
            # 指令細化
            if r['Bias'] > 25: action = "🚫 絕不追高"
            elif r['Score'] > 85 and r['Dist'] < 2.0: action = "🔥 先勝狙擊!"
            elif r['Bias'] < 8: action = "🎯 底部潛伏"
            else: action = f"觀察(距買點{r['Dist']:.1f}%)"
            
            # 板塊共振標籤
            t_display = ("🐺" if sector_map.get(r['Sec'], 0) >= 3 else "") + r['T']
            
            top10.append([
                f"T{len(top10)+1}", t_display, r['Sec'], round(r['P'], 2), f"{r['1D']:.1f}%", f"{r['ADR']:.1f}%",
                f"{r['Bias']:.1f}%", r['Trend'], f"{r['RPS']:.1f}", f"R40({r['Fin']:.0f}%)", f"{r['Score']:.1f}", action
            ])
            counts[r['Sec']] = counts.get(r['Sec'], 0) + 1
        if len(top10) >= 10: break

    header = [
        ["🏰 V80.5 Master Sniper 先勝後戰版", "更新:", datetime.datetime.now().strftime('%m-%d %H:%M'), "VIX:", f"{vix:.1f}", "戰略:", "只打有把握之仗", "", "", "", "", ""],
        ["排名", "代碼", "板塊", "現價", "1D%", "ADR", "50MA乖離", "60日趨勢", "RPS總分", "基本面", "先勝評分", "作戰指令"]
    ]
    sync_to_google_sheet("🚀右側_動能成長", header + top10)

if __name__ == "__main__":
    run_right_side_momentum()
