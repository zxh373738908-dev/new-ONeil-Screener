import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import requests
import json
import warnings
import math
import urllib.request
import time
import random
from concurrent.futures import ThreadPoolExecutor

warnings.filterwarnings('ignore')

# ==========================================
# 1. 系統配置中心
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"
TARGET_SHEET = "super"
YTD_BASE_DATE = "2025-12-31"

def get_universe():
    # 核心深潛清單 (加入原作者與你關注的強勢股)
    core = ["CAVA", "FIVE", "HWM", "PWR", "VRT", "MPWR", "DOCN", "APP", "PLTR", "SMCI", "LITE", "TER", "KEYS", "MU", "DELL", "WDC", "STX", "WM", "LIN", "LRCX", "AVGO", "NVDA", "GEV", "ALB", "ROKU", "GNRC", "MRNA", "FIX"]
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', headers=headers, timeout=15)
        sp500 = pd.read_html(res.text)[0]['Symbol'].tolist()
        return list(set([t.replace('.', '-') for t in sp500] + core))
    except: return core

EXCLUDED = ['Banks', 'Insurance', 'Financial', 'REIT', 'Utilities', 'Oil & Gas']

# ==========================================
# 2. 工具函數
# ==========================================
def fetch_info_v81(t):
    ticker = yf.Ticker(t)
    try:
        time.sleep(random.uniform(0.3, 0.6))
        info = ticker.info
        if info and 'industry' in info:
            info['industry'] = str(info['industry']).strip().replace('\t', '')
            return t, info
    except: pass
    try:
        fast = ticker.fast_info
        return t, {'industry': 'Growth/Tech', 'sector': 'Technology', 'marketCap': fast.get('market_cap', 0), 'revenueGrowth': 0.15}
    except: return t, {}

def get_ret(series, days):
    if series is None or len(series) < days + 1: return 0.0
    return (series.iloc[-1] / series.iloc[-(days+1)]) - 1

# ==========================================
# 3. 核心量化模型 V81
# ==========================================
def run_super_growth_v81():
    update_time = datetime.datetime.now().strftime('%m-%d %H:%M')
    universe = get_universe()
    print("\n" + "="*50)
    print(f"🚀 [超級成長股 V81] 啟動 | Master Sniper 模式...")

    # 1. 宏觀與天氣 (圖一強項)
    try:
        macro_list = ["SPY", "^VIX", "BNO", "GLD", "CPER"]
        m_data = yf.download(macro_list, start="2024-09-01", progress=False)['Close'].dropna()
        spy_hist = m_data['SPY']
        vix_val = float(m_data['^VIX'].iloc[-1])
        bno_p, gld_p, cper_p = m_data['BNO'].iloc[-1], m_data['GLD'].iloc[-1], m_data['CPER'].iloc[-1]
        
        curr_spy, ma50_spy = spy_hist.iloc[-1], spy_hist.tail(50).mean()
        spy_r = {20: get_ret(spy_hist, 20), 60: get_ret(spy_hist, 60), 120: get_ret(spy_hist, 120)}
        
        # 💡 圖二風格：戰略指令
        strategy = "全面進攻" if curr_spy > ma50_spy and vix_val < 18 else ("先勝後戰" if curr_spy > ma50_spy else "戰略撤退")
        weather = "☀️" if curr_spy > ma50_spy and vix_val < 21 else ("☁️" if curr_spy > ma50_spy else "⛈️")
    except: strategy, weather, vix_val, spy_r = "數據受限", "❓", 19.0, {20:0, 60:0, 120:0}

    # 2. 技術面深潛掃描
    print(f"📡 正在掃描 {len(universe)} 隻標的...")
    hist_all = yf.download(universe, start="2024-09-01", progress=False, threads=True)
    close_df, high_df, low_df = hist_all['Close'], hist_all['High'], hist_all['Low']

    tech_results, above_50ma, perfect_tickers = {}, 0, []
    total_valid = 0

    for t in universe:
        try:
            if t not in close_df.columns: continue
            c, h, l = close_df[t].dropna(), high_df[t].dropna(), low_df[t].dropna()
            if len(c) < 220: continue 
            
            total_valid += 1
            p = float(c.iloc[-1])
            m20, m50, m200 = c.tail(20).mean(), c.tail(50).mean(), c.tail(200).mean()
            
            if p > m50: above_50ma += 1
            if p > m20 > m50 > m200: perfect_tickers.append(t)
            if not (p > m50): continue 
            
            # 💡 圖二核心：計算買點距離 (距離 20EMA 的距離)
            ema20 = c.ewm(span=20, adjust=False).mean().iloc[-1]
            dist_to_buy = ((p - ema20) / ema20) * 100
            
            # Sparkline
            prices_60 = c.tail(60).tolist()
            spark_data = ",".join([str(round(v, 2)) for v in prices_60])
            spark_formula = f'=SPARKLINE({{{spark_data}}}, {{"charttype","line";"linewidth",2;"color","blue"}})'
            
            tech_results[t] = {
                "Price": p, "1D": (c.iloc[-1]/c.iloc[-2])-1,
                "Trend": spark_formula, "Dist": dist_to_buy,
                "VolRatio": hist_all['Volume'][t].iloc[-1] / hist_all['Volume'][t].tail(20).mean() if t in hist_all['Volume'] else 1,
                "RS_Raw": (get_ret(c, 21) * 0.4) + (get_ret(c, 63) * 0.3) + (get_ret(c, 126) * 0.3),
                "YTD": (p / c.asof(pd.Timestamp(YTD_BASE_DATE))) - 1,
                "REL20": get_ret(c, 20) - spy_r[20], "REL60": get_ret(c, 60) - spy_r[60], 
                "REL120": get_ret(c, 120) - spy_r[120], "H60": h.tail(60).max(),
                "ADR": ((h - l) / l).tail(20).mean() * 100
            }
        except: continue

    # 3. 基本面 (慢速)
    infos = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        for t, info in executor.map(fetch_info_v81, list(tech_results.keys())):
            if info: infos[t] = info

    res_map = {}
    for t in perfect_tickers:
        ind = infos.get(t, {}).get('industry') or "Unknown"
        res_map[ind] = res_map.get(ind, 0) + 1

    # 4. 決策矩陣
    rs_ranks = (pd.Series({t: d['RS_Raw'] for t, d in tech_results.items()}).rank(pct=True) * 100).to_dict()
    all_cands = []
    for t, data in tech_results.items():
        if t not in infos: continue
        info = infos[t]
        sec, ind = str(info.get('sector', 'Unknown')), str(info.get('industry', 'Unknown'))
        if any(ex.lower() in ind.lower() for ex in EXCLUDED): continue
        
        rs = rs_ranks.get(t, 0)
        rev_g = (info.get('revenueGrowth', 0) or 0) * 100
        score = (rs * 0.7) + (rev_g * 0.3)
        
        # 💡 圖二的核心：作戰指令與評分
        dist = data['Dist']
        if rs < 80: action = "⚠️ 汰換"
        elif dist <= 2.5 and dist >= -0.5: action = "🎯 買點區"
        elif dist > 15: action = "🚫 絕不追高"
        else: action = f"觀察(距買點{round(dist,1)}%)"

        # 基礎評分 (用於圖二 Rating 欄位)
        rating = (rs * 0.6) + (rev_g * 0.2) - (abs(dist) * 2)

        all_cands.append({
            "T": t, "Sec": sec, "Ind": ind[:16], "Score": score, "Action": action, "Rate": rating,
            "YTD": data['YTD'], "Trend": data['Trend'], "RS": rs,
            "REL20": data['REL20'], "REL60": data['REL60'], "REL120": data['REL120'],
            "Res": f"{res_map.get(ind, 0)}隻", "ADR": data['ADR'], "Vol": data['VolRatio'],
            "MCap": info.get('marketCap', 0)/1e6, "P": data['Price'], "1D": data['1D'],
            "VP": f"${round(data['H60']*0.95, 1)}(突)" if data['Price'] > data['H60']*0.95 else f"${round(data['H60'], 1)}(壓)"
        })

    # 板塊與行業雙重隔離
    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_10, s_cnt, i_cnt = [], {}, {}
    for r in all_cands:
        if s_cnt.get(r['Sec'], 0) >= 3 or i_cnt.get(r['Ind'], 0) >= 1: continue
        top_10.append(r)
        s_cnt[r['Sec']] = s_cnt.get(r['Sec'], 0) + 1
        i_cnt[r['Ind']] = i_cnt.get(r['Ind'], 0) + 1
        if len(top_10) >= 10: break

    # ==========================================
    # 5. 輸出矩陣 (V81 精確版)
    # ==========================================
    headers = ["排名", "代碼", "板塊", "評分", "作戰指令", "基本面標籤", "今年YTD", "近60日趨勢(圖)", "REL20", "REL60", "REL120", "RS_Rank", "行業共振", "ADR", "量比", "價格", "1D%", "MktCap", "籌碼峰", "Score", "更新"]
    
    us_breadth = (above_50ma / total_valid * 100) if total_valid > 0 else 0
    m_info = f"天氣:{weather} | 寬度:{us_breadth:.1f}% | 共振:{len(perfect_tickers)}隻 | VIX:{round(vix_val, 1)} | 戰略:{strategy}"
    
    row1 = [f"Master Sniper V81 Deep Dive", f"更新: {update_time}", m_info] + [""] * (len(headers) - 3)
    
    matrix = [row1, headers]
    for i, r in enumerate(top_10):
        matrix.append([
            f"T{i+1}", r['T'], r['Ind'], round(r['Rate'], 1), r['Action'], r['Msg'] if 'Msg' in r else "R40/利潤",
            f"{round(r['YTD']*100, 2)}%", r['Trend'], f"{round(r['REL20']*100, 2)}%", f"{round(r['REL60']*100, 2)}%", f"{round(r['REL120']*100, 2)}%",
            round(r['RS'], 1), r['Res'], f"{round(r['ADR'], 2)}%", f"{round(r['Vol'], 2)}x",
            f"${round(r['P'], 2)}", f"{r['1D']*100:+.2f}%", round(r['MCap'], 1), r['VP'], round(r['Score'], 1), update_time
        ])

    sync_to_google_sheet(TARGET_SHEET, matrix)

if __name__ == "__main__":
    run_super_growth_v81()
