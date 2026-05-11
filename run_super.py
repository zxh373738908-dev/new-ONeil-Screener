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
    core = ["CAVA", "FIVE", "HWM", "PWR", "VRT", "MPWR", "DOCN", "APP", "PLTR", "SMCI", "LITE", "TER", "KEYS", "MU", "DELL", "WDC", "STX", "WM", "LIN", "LRCX", "AVGO", "NVDA", "GEV", "ALB", "ROKU", "GNRC", "MRNA", "FIX"]
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', headers=headers, timeout=15)
        sp500 = pd.read_html(res.text)[0]['Symbol'].tolist()
        return list(set([t.replace('.', '-') for t in sp500] + core))
    except: return core

EXCLUDED = ['Banks', 'Insurance', 'Financial', 'REIT', 'Utilities', 'Oil & Gas']

# ==========================================
# 2. 核心工具函數 (修復 NameError)
# ==========================================
def sync_to_google_sheet(sheet_name, matrix):
    """發送數據到 Google Sheets"""
    try:
        payload = {"sheet_name": sheet_name, "data": json.loads(json.dumps(matrix, default=str))}
        response = requests.post(WEBAPP_URL, json=payload, timeout=50)
        if response.status_code == 200:
            print(f"🎉 同步成功至分頁: [{sheet_name}]")
        else:
            print(f"❌ 同步異常: {response.status_code}")
    except Exception as e:
        print(f"❌ 同步失敗: {e}")

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
# 3. 核心量化模型 V81.1
# ==========================================
def run_super_growth_v81():
    update_time = datetime.datetime.now().strftime('%m-%d %H:%M:%S')
    universe = get_universe()
    print("\n" + "="*50)
    print(f"🚀 [超級成長股 V81.1] 啟動 | 深度狙擊模式...")

    # 1. 宏觀與天氣 (解決 VIX 0.0 問題)
    try:
        macro_list = ["SPY", "^VIX", "BNO", "GLD", "CPER"]
        m_data = yf.download(macro_list, period="2y", progress=False)['Close'].dropna()
        spy_hist = m_data['SPY']
        
        # 💡 VIX 暴力修正邏輯
        vix_val = float(m_data['^VIX'].iloc[-1])
        if vix_val < 0.1: # 如果 download 失敗，嘗試 history
            vix_val = float(yf.Ticker("^VIX").history(period="5d")['Close'].iloc[-1])
        
        bno_p, gld_p, cper_p = m_data['BNO'].iloc[-1], m_data['GLD'].iloc[-1], m_data['CPER'].iloc[-1]
        spy_r = {20: get_ret(spy_hist, 20), 60: get_ret(spy_hist, 60), 120: get_ret(spy_hist, 120)}
        curr_spy, ma50_spy = spy_hist.iloc[-1], spy_hist.tail(50).mean()
        
        strategy = "全面進攻" if curr_spy > ma50_spy and vix_val < 18 else ("先勝後戰" if curr_spy > ma50_spy else "戰略撤退")
        weather = "☀️" if curr_spy > ma50_spy and vix_val < 22 else ("☁️" if curr_spy > ma50_spy else "⛈️")
        macro_text = f"BNO:${bno_p:.1f} | 銅金比:{cper_p/gld_p:.3f} | 油金比:{bno_p/gld_p:.3f}"
    except: 
        strategy, weather, vix_val, spy_r, macro_text = "等待數據", "❓", 19.0, {20:0, 60:0, 120:0}, "宏觀掃描中"

    # 2. 技術面掃描
    print(f"📡 正在掃描 {len(universe)} 隻標的...")
    hist_all = yf.download(universe, period="2y", progress=False, threads=True)
    close_df, vol_df, high_df, low_df = hist_all['Close'], hist_all['Volume'], hist_all['High'], hist_all['Low']

    tech_results, above_50ma, perfect_tickers = {}, 0, []
    total_valid = 0

    for t in universe:
        try:
            if t not in close_df.columns: continue
            c, v, h, l = close_df[t].dropna(), vol_df[t].dropna(), high_df[t].dropna(), low_df[t].dropna()
            if len(c) < 200: continue 
            
            total_valid += 1
            p = float(c.iloc[-1])
            m20, m50, m200 = c.tail(20).mean(), c.tail(50).mean(), c.tail(200).mean()
            
            if p > m50: above_50ma += 1
            if p > m20 > m50 > m200: perfect_tickers.append(t)
            if not (p > m50): continue 
            
            ema20 = c.ewm(span=20, adjust=False).mean().iloc[-1]
            dist_to_buy = ((p - ema20) / ema20) * 100
            
            # Sparkline 公式
            prices_60 = c.tail(60).tolist()
            spark_data = ",".join([str(round(val, 2)) for val in prices_60])
            spark_formula = f'=SPARKLINE({{{spark_data}}}, {{"charttype","line";"linewidth",2;"color","blue"}})'
            
            tech_results[t] = {
                "Price": p, "1D": (c.iloc[-1]/c.iloc[-2])-1,
                "Trend": spark_formula, "Dist": dist_to_buy,
                "VolRatio": v.iloc[-1] / v.tail(20).mean() if not v.empty else 1,
                "RS_Raw": (get_ret(c, 21) * 0.4) + (get_ret(c, 63) * 0.3) + (get_ret(c, 126) * 0.3),
                "YTD": (p / c.asof(pd.Timestamp(YTD_BASE_DATE))) - 1,
                "REL20": get_ret(c, 20) - spy_r[20], "REL60": get_ret(c, 60) - spy_r[60], 
                "REL120": get_ret(c, 120) - spy_r[120], "H60": h.tail(60).max(),
                "ADR": ((h - l) / l).tail(20).mean() * 100
            }
        except: continue

    # 3. 獲取基本面 (慢速並行)
    print(f"✅ 技術過濾剩餘 {len(tech_results)} 隻，獲取基本面信息...")
    infos = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        for t, info in executor.map(fetch_info_v81, list(tech_results.keys())):
            if info: infos[t] = info

    res_map = {}
    for t in perfect_tickers:
        ind = infos.get(t, {}).get('industry') or "Unknown"
        res_map[ind] = res_map.get(ind, 0) + 1

    # 4. 決策與打分
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
        
        # 💡 Master Sniper 專屬指令
        dist = data['Dist']
        if rs < 80: action = "⚠️ 汰換"
        elif dist <= 2.2 and dist >= -0.5: action = "🎯 買點區"
        elif dist > 15: action = "🚫 絕不追高"
        else: action = f"觀察(距買點{round(dist,1)}%)"

        # 基本面標籤 Msg
        fcf_m = ((info.get('freeCashflow', 0) or 0) / (info.get('totalRevenue', 1) or 1)) * 100
        msg = f"R40({round(rev_g + fcf_m)}%)" if 'Tech' in sec else f"利潤({round(info.get('operatingMargins', 0)*100, 1)}%)"
        if data['VolRatio'] > 1.3: msg += f" | 📈爆量"

        all_cands.append({
            "T": t, "Sec": sec, "Ind": ind[:16], "Score": score, "Action": action, "Msg": msg,
            "YTD": data['YTD'], "Trend": data['Trend'], "RS": rs, "Rate": (rs * 0.6) + (rev_g * 0.2) - (abs(dist) * 2),
            "REL20": data['REL20'], "REL60": data['REL60'], "REL120": data['REL120'],
            "Res": f"{res_map.get(ind, 0)}隻", "ADR": data['ADR'], "Vol": data['VolRatio'],
            "MCap": info.get('marketCap', 0)/1e6, "P": data['Price'], "1D": data['1D'],
            "VP": f"${round(data['H60']*0.95, 1)}(突)" if data['Price'] > data['H60']*0.95 else f"${round(data['H60'], 1)}(壓)"
        })

    # 板塊隔離
    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_10, s_cnt, i_cnt = [], {}, {}
    for r in all_cands:
        if s_cnt.get(r['Sec'], 0) >= 3 or i_cnt.get(r['Ind'], 0) >= 1: continue
        top_10.append(r)
        s_cnt[r['Sec']] = s_cnt.get(r['Sec'], 0) + 1
        i_cnt[r['Ind']] = i_cnt.get(r['Ind'], 0) + 1
        if len(top_10) >= 10: break

    # ==========================================
    # 5. 精確輸出 (21列格式)
    # ==========================================
    headers = ["排名", "代碼", "板塊", "評分", "作戰指令", "基本面標籤", "今年YTD", "近60日趨勢(圖)", "REL20", "REL60", "REL120", "RS_Rank", "行業共振", "ADR", "量比", "價格", "1D%", "MktCap", "籌碼峰", "Score", "更新時間"]
    
    us_breadth = (above_50ma / total_valid * 100) if total_valid > 0 else 0
    m_info = f"天氣:{weather} | 寬度:{us_breadth:.1f}% | 共振:{len(perfect_tickers)}隻 | VIX:{round(vix_val, 1)} | 戰略:{strategy} | {macro_text}"
    
    row1 = [f"Master Sniper V81.1 Final", f"更新: {update_time}", m_info] + [""] * (len(headers) - 3)
    
    matrix = [row1, headers]
    for i, r in enumerate(top_10):
        t_disp = f"👑 {r['T']}" if i < 3 else r['T']
        def f_p(v): return f"{round(v*100, 2)}%"
        # 💡 強制 Score/Rank/MktCap 變為帶一個空格的字串，徹底阻斷百分比格式
        matrix.append([
            f"T{i+1}", t_disp, r['Ind'], f"{round(r['Rate'], 1)} ", r['Action'], r['Msg'],
            f_p(r['YTD']), r['Trend'], f_p(r['REL20']), f_p(r['REL60']), f_p(r['REL120']),
            f"{round(r['RS'], 1)} ", r['Res'], f"{round(r['ADR'], 2)}%", f"{round(r['Vol'], 2)}x",
            f"${round(r['P'], 2)}", f"{r['1D']*100:+.2f}%", f"{round(r['MCap'], 1)} ",
            r['VP'], f"{round(r['Score'], 1)} ", update_time
        ])

    sync_to_google_sheet(TARGET_SHEET, matrix)

if __name__ == "__main__":
    run_super_growth_v81()
