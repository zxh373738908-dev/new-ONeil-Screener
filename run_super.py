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
    # 💡 核心進化：精準定位大神最新持倉池 (DUOL, NTNX, OKTA, FSLR, V, NDAQ)
    master_current = ["DUOL", "FSLR", "LLY", "NDAQ", "NTNX", "OKTA", "PWR", "ROKU", "V", "VRT"]
    # 大師核心觀察池
    core_watchlist = master_current + ["CAVA", "FIVE", "HWM", "MPWR", "LITE", "MU", "SNDK", "GEV", "ALB", "SMCI", "SNPS", "AVGO", "LRCX"]
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', headers=headers, timeout=15)
        sp500 = pd.read_html(res.text)[0]['Symbol'].tolist()
        return list(set([t.replace('.', '-') for t in sp500] + core_watchlist))
    except: return core_watchlist

# 💡 放行金融基礎設施與服務 (如 Visa, NDAQ, LLY)，只攔截傳統商業銀行與地產
EXCLUDED = ['Commercial Banks', 'Savings Institutions', 'Mortgage', 'Real Estate']

# ==========================================
# 2. 核心避錯與計算函數
# ==========================================
def fetch_info_v84(t):
    ticker = yf.Ticker(t)
    try:
        time.sleep(random.uniform(0.3, 0.6))
        info = ticker.info
        if info and ('industry' in info):
            info['industry'] = str(info['industry']).strip().replace('\t', '')
            return t, info
    except: pass
    try:
        fast = ticker.fast_info
        return t, {'industry': 'Growth/Service', 'sector': 'Technology', 'marketCap': fast.market_cap, 'revenueGrowth': 0.1}
    except: return t, {}

def sync_to_google_sheet(sheet_name, matrix):
    try:
        payload = {"sheet_name": sheet_name, "data": json.loads(json.dumps(matrix, default=str))}
        requests.post(WEBAPP_URL, json=payload, timeout=50)
        print(f"🎉 V84 大師同步版 同步成功！")
    except Exception as e: print(f"❌ 同步失敗: {e}")

def get_ret(series, days):
    if series is None or len(series) < days + 1: return 0.0
    return (series.iloc[-1] / series.iloc[-(days+1)]) - 1

def f_pct(v): return f"{round(v*100, 2)}%" if not pd.isna(v) else "0.00%"
def f_num(v): return f"{round(v, 1)}" if not pd.isna(v) else "0.0"
def f_price(v): return f"${round(v, 2)}" if not pd.isna(v) else "$0.00"

# ==========================================
# 3. 核心量化模型 V84 (大師轉向優化)
# ==========================================
def run_super_growth_v84():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = get_universe()
    print("\n" + "="*50)
    print(f"🚀 [超級成長股 V84] 啟動 | 正在模擬大師的軟體轉向與防禦佈陣...")

    # 1. 大盤與宏觀
    try:
        m_data = yf.download(["SPY", "^VIX", "BNO", "GLD", "CPER"], period="2y", progress=False)['Close'].dropna()
        spy_hist = m_data['SPY']
        vix_val = float(m_data['^VIX'].iloc[-1])
        if vix_val < 0.1: vix_val = float(yf.Ticker("^VIX").history(period="5d")['Close'].iloc[-1])
        spy_r = {20: get_ret(spy_hist, 20), 60: get_ret(spy_hist, 60), 120: get_ret(spy_hist, 120)}
        curr_spy, ma50_spy = float(spy_hist.iloc[-1]), float(spy_hist.tail(50).mean())
        
        weather = "☀️" if curr_spy > ma50_spy and vix_val < 22 else ("☁️" if curr_spy > ma50_spy else "⛈️")
        strategy = "軟體與防禦優先" if vix_val > 18 else "全面進攻"
        macro_text = f"BNO:${float(m_data['BNO'].iloc[-1]):.1f} | 銅金比:{float(m_data['CPER'].iloc[-1]/m_data['GLD'].iloc[-1]):.3f}"
    except: 
        weather, vix_val, spy_r, strategy, macro_text = "❓", 19.0, {20:0,60:0,120:0}, "等待數據", "數據掃描中"

    # 2. 技術面掃描
    print(f"📡 下載 K 線並計算 Bias...")
    hist_all = yf.download(universe, period="2y", progress=False, threads=True)
    close_df = hist_all['Close']

    tech_results, above_50ma, perfect_tickers = {}, 0, []

    for t in universe:
        try:
            if t not in close_df.columns: continue
            c = close_df[t].dropna()
            if len(c) < 220: continue 
            
            p = float(c.iloc[-1])
            m20, m50, m200 = c.tail(20).mean(), c.tail(50).mean(), c.tail(200).mean()
            
            if p > m50: above_50ma += 1
            if p > m20 > m50 > m200: perfect_tickers.append(t)
            if not (p > m50): continue 
            
            # 💡 偷師大師：計算風險，並加入 60 日趨勢圖
            ema20 = c.ewm(span=20, adjust=False).mean().iloc[-1]
            risk = ((ema20 - p) / p) * 100
            
            spark_formula = f'=SPARKLINE({{{",".join([str(round(v,2)) for v in c.tail(60).tolist()])}}}, {{"charttype","line";"linewidth",2;"color","blue"}})'
            
            tech_results[t] = {
                "Price": p, "1D": (c.iloc[-1]/c.iloc[-2])-1, "Trend": spark_formula, "Risk": risk,
                "VolRatio": hist_all['Volume'][t].iloc[-1] / hist_all['Volume'][t].tail(20).mean() if t in hist_all['Volume'] else 1,
                "RS_Raw": (get_ret(c, 21) * 0.4) + (get_ret(c, 63) * 0.3) + (get_ret(c, 126) * 0.3),
                "YTD": (p / c.loc[c.index <= YTD_BASE_DATE].iloc[-1]) - 1 if not c.loc[c.index <= YTD_BASE_DATE].empty else 0,
                "ADR": ((hist_all['High'][t].dropna() - hist_all['Low'][t].dropna()) / hist_all['Low'][t].dropna()).tail(20).mean() * 100,
                "R20": get_ret(c, 20), "R60": get_ret(c, 60), "R120": get_ret(c, 120),
                "REL20": get_ret(c, 20) - spy_r[20], "REL60": get_ret(c, 60) - spy_r[60], "REL120": get_ret(c, 120) - spy_r[120],
                "H60": hist_all['High'][t].tail(60).max()
            }
        except: continue

    # 3. 基本面
    infos = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        for t, info in executor.map(fetch_info_v84, list(tech_results.keys())):
            if info: infos[t] = info

    res_map = {t: infos.get(t, {}).get('industry', 'Unknown') for t in perfect_tickers}
    ind_res_counts = pd.Series(res_map.values()).value_counts().to_dict()

    # 4. 打分與過濾 (注入大師基因)
    rs_ranks = (pd.Series({t: d['RS_Raw'] for t, d in tech_results.items()}).rank(pct=True) * 100).to_dict()
    all_cands = []
    for t, data in tech_results.items():
        if t not in infos: continue
        info = infos[t]
        sec, ind = str(info.get('sector', 'Unknown')), str(info.get('industry', 'Unknown'))
        if any(ex.lower() in ind.lower() for ex in EXCLUDED): continue
        
        rs = rs_ranks.get(t, 0)
        # 💡 大師修正：如果 Bias(風險) > 15%，強制分數大幅下降 (拒絕追高)
        risk_val = data['Risk']
        score = (rs * 0.7) + ((info.get('revenueGrowth', 0) or 0) * 100 * 0.3)
        if risk_val < -15.0: score -= 30 
        
        action = f"🎯狙擊({round(risk_val,1)}%)" if -3.5 <= risk_val <= 0.8 else f"觀察({round(risk_val,1)}%)"
        if rs < 80: action = "⚠️汰換"

        msg = f"利潤({round(info.get('operatingMargins', 0)*100, 1)}%)"
        if data['VolRatio'] > 1.3: msg += f"|📈爆量"

        all_cands.append({
            "Ticker": t, "Sector": sec, "Industry": ind, "Score": score, "Action": action, "Msg": msg,
            "YTD": data['YTD'], "Trend": data['Trend'], "RS": rs, "Rate": (rs*0.6) - (abs(risk_val)*2),
            "REL20": data['REL20'], "REL60": data['REL60'], "REL120": data['REL120'],
            "Res": f"{ind_res_counts.get(ind, 0)}隻", "ADR": data['ADR'], "Vol": data['VolRatio'],
            "MCap": info.get('marketCap', 0)/1e6, "Price": data['Price'], "1D": data['1D'],
            "VPOC": f"${round(data['H60']*0.95, 1)}(突)" if data['Price'] > data['H60']*0.95 else f"${round(data['H60'], 1)}(壓)"
        })

    # 5. 排序與輸出
    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_10, s_cnt, i_cnt = [], {}, {}
    for r in all_cands:
        if s_cnt.get(r['Sector'], 0) >= 3 or i_cnt.get(r['Industry'], 0) >= 1: continue
        top_10.append(r)
        s_cnt[r['Sector']] = s_cnt.get(r['Sector'], 0) + 1
        i_cnt[r['Industry']] = i_cnt.get(r['Industry'], 0) + 1
        if len(top_10) >= 12: break

    headers = ["排名", "代碼", "板塊", "評分", "作戰指令", "Msg標籤", "今年YTD", "60日趨勢(圖)", "REL20", "REL60", "REL120", "RS_Rank", "行業共振", "ADR", "量比", "價格", "1D%", "MktCap", "籌碼峰", "Score", "盤建", "更新時間"]
    us_breadth = (above_50ma / len(universe) * 100) if universe else 0
    m_info = f"天氣:{weather} | 寬度:{us_breadth:.1f}% | 共振:{len(perfect_tickers)}隻 | VIX:{round(vix_val, 1)} | 戰略:{strategy} | {macro_text}"
    
    matrix = [[f"Master Sniper V84 (Master Rotation)", f"更新: {update_time}", m_info] + [""] * (len(headers) - 3), headers]
    for i, r in enumerate(top_10):
        t_disp = f"👑 {r['Ticker']}" if i < 3 else r['Ticker']
        matrix.append([f"T{i+1}", t_disp, r['Industry'][:16], f"{round(r['Rate'], 1)} ", r['Action'], r['Msg'], f_pct(r['YTD']), r['Trend'], f_pct(r['REL20']), f_pct(r['REL60']), f_pct(r['REL120']), f"{round(r['RS'], 1)} ", r['Res'], f"{round(r['ADR'], 2)}%", f"{round(r['Vol'], 2)}x", f_price(r['Price']), f_1d(r['1D']), f"{round(r['MCap'], 1)} ", r['VPOC'], f"{round(r['Score'], 1)} ", "✅ 持有", update_time])

    sync_to_google_sheet(TARGET_SHEET, matrix)

if __name__ == "__main__":
    run_super_growth_v84()
