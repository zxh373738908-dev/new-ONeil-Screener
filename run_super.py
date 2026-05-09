import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import requests
import json
import warnings
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

GURU_LIST =["CVNA", "ROKU", "CAVA", "FIVE", "HWM", "PWR", "VRT", "MPWR", "DOCN", "APP", "PLTR", "SMCI", "LITE", "TER", "KEYS", "MU", "DELL", "STX", "WDC", "STLD", "ALB", "GEV", "SATS"]
BLACK_LIST =["MAR", "ATVI", "FB", "TWTR"]

def get_universe_v73():
    try:
        ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        req = urllib.request.Request('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', headers={'User-Agent': ua})
        res = urllib.request.urlopen(req, timeout=20)
        df = pd.read_html(res.read())[0]
        sp500 = [t.replace('.', '-') for t in df['Symbol'].tolist() if t.replace('.', '-') not in BLACK_LIST]
        return list(set(sp500 + GURU_LIST))
    except: return GURU_LIST

EXCLUDED =['Banks', 'Insurance', 'Financial', 'REIT', 'Utilities', 'Oil & Gas']

# ==========================================
# 2. 輔助函數
# ==========================================
def fetch_info_v73(t):
    ticker = yf.Ticker(t)
    for i in range(2):
        try:
            time.sleep(random.uniform(0.2, 0.4))
            info = ticker.info
            if info and 'industry' in info:
                info['industry'] = str(info['industry']).strip().replace('\t', '')
                return t, info
        except: time.sleep(1)
    return t, {}

def get_ret(series, days):
    if series is None or len(series) < days + 1: return 0.0
    return (series.iloc[-1] / series.iloc[-(days+1)]) - 1

# ==========================================
# 3. 核心量化模型 V73
# ==========================================
def run_super_growth_v73():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = get_universe_v73()
    print("\n" + "="*50)
    print(f"🚀 [超級成長股 V73] 啟動 | 載入現貨/期貨雙軌恐慌雷達...")

    # 1. 抓取大盤與 💡「雙軌 VIX 引擎」
    try:
        m_list =["SPY", "BNO", "GLD", "CPER"]
        m_data = yf.download(m_list, start="2024-09-01", progress=False)['Close'].ffill()
        spy = m_data['SPY'].dropna()
        
        # 💡 抓取 VIX 現貨 (用於真實天氣判定)
        try: vix_spot = float(yf.Ticker("^VIX").fast_info.last_price)
        except: vix_spot = float(yf.download("^VIX", period="5d", progress=False)['Close'].dropna().iloc[-1])
        
        # 💡 抓取 VIX 期貨 (用於夜盤預警，可能失敗但不影響主程式)
        try: vix_fut = float(yf.Ticker("VX=F").fast_info.last_price)
        except: vix_fut = vix_spot
            
        bno_p, gld_p, cper_p = float(m_data['BNO'].iloc[-1]), float(m_data['GLD'].iloc[-1]), float(m_data['CPER'].iloc[-1])
        bno_1d = (bno_p / float(m_data['BNO'].iloc[-2])) - 1 if len(m_data['BNO']) > 1 else 0
        spy_r = {20: get_ret(spy, 20), 60: get_ret(spy, 60), 120: get_ret(spy, 120)}
        curr_spy, ma20_spy, ma50_spy = spy.iloc[-1], spy.tail(20).mean(), spy.tail(50).mean()
        
        # 💡 使用真實的現貨 VIX 判定天氣 (防止升水導致的假警報)
        if vix_spot >= 22: weather = "⛈️"
        elif curr_spy > ma50_spy and vix_spot < 20: weather = "☀️"
        else: weather = "☁️"
        
        war_alert = "🚨【地緣預警】" if bno_1d > 0.035 and vix_spot > 19 else ("🛡️【避險啟動】" if curr_spy < ma20_spy and vix_spot > 20 else "✅ 環境平穩")
        macro_text = f"BNO:${bno_p:.1f}({bno_1d*100:+.1f}%)|銅金比:{cper_p/gld_p:.3f}|{war_alert}"
    except: weather, vix_spot, vix_fut, spy_r, macro_text, curr_spy, ma20_spy = "🌤️", 18.0, 18.0, {20:0, 60:0, 120:0}, "數據受限", 500, 500

    # 2. 技術掃描
    hist_all = yf.download(universe, start="2024-09-01", progress=False, threads=True)
    close_df, vol_df, high_df, low_df = hist_all['Close'], hist_all['Volume'], hist_all['High'], hist_all['Low']

    tech_pool, perfect_tickers, above_50ma, total_valid = {},[], 0, 0
    for t in universe:
        try:
            if t not in close_df.columns: continue
            c, h, l, v = close_df[t].dropna(), high_df[t].dropna(), low_df[t].dropna(), vol_df[t].dropna()
            if len(c) < 150: continue
            p = float(c.iloc[-1])
            m20, m50, m200 = c.tail(20).mean(), c.tail(50).mean(), c.tail(200).mean()
            
            total_valid += 1
            if p > m50: above_50ma += 1
            if p > m20 > m50 > m200: perfect_tickers.append(t)
            if p < m50: continue 
            
            risk = ((c.ewm(span=20, adjust=False).mean().iloc[-1] - p) / p) * 100
            spark = ",".join([str(round(val, 2)) for val in c.tail(60).tolist()])
            
            tech_pool[t] = {
                "P": p, "1D": (c.iloc[-1]/c.iloc[-2])-1, "Risk": risk,
                "VR": v.iloc[-1] / v.tail(20).mean() if not v.empty else 1.0,
                "RS_Raw": (get_ret(c, 21)*0.4) + (get_ret(c, 63)*0.4) + (get_ret(c, 126)*0.2),
                "YTD": (p / (c.asof(pd.Timestamp(YTD_BASE_DATE)) or c.iloc[0])) - 1,
                "ADR": ((h - l) / l).tail(20).mean() * 100,
                "R20": get_ret(c, 20) - spy_r.get(20, 0), "R60": get_ret(c, 60) - spy_r.get(60, 0), "R120": get_ret(c, 120) - spy_r.get(120, 0),
                "Spark": spark, "H60": h.tail(60).max()
            }
        except: continue

    # 3. 獲取基本面
    infos = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        for t, info in executor.map(fetch_info_v73, list(tech_pool.keys())):
            if info: infos[t] = info

    res_map = {}
    for t in perfect_tickers:
        ind = infos.get(t, {}).get('industry') or "Unknown"
        res_map[ind] = res_map.get(ind, 0) + 1

    # 4. 打分與排名
    rs_ranks = (pd.Series({t: d['RS_Raw'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()
    all_cands =[]
    for t, data in tech_pool.items():
        if t not in infos: continue
        info, rs = infos[t], rs_ranks.get(t, 0)
        if rs < 85: continue 
        sec, ind = str(info.get('sector', 'Unknown')), str(info.get('industry', 'Unknown'))
        if any(ex.lower() in ind.lower() for ex in EXCLUDED): continue
        
        rev_g = (info.get('revenueGrowth', 0) or 0) * 100
        score = (rs * 0.75) + (rev_g * 0.25)
        risk_v = round(data['Risk'], 1)
        
        if -2.8 <= risk_v <= 1.0: action = f"🎯狙擊({risk_v}%)  "; score *= 1.5
        elif risk_v < -2.8: action = f"⌛等回({risk_v}%)  "; score *= (0.8 if risk_v < -12 else 1.0)
        else: action = f"📉破線({risk_v}%)  "
        if t in GURU_LIST: score *= 1.15

        msg = f"RPS:{round(rs,1)}|RevG:{round(rev_g)}%"
        all_cands.append({
            "Ticker": t, "Sector": sec, "Industry": ind[:16], "Score": score, "Action": action, "Msg": msg,
            "YTD": data['YTD'], "Trend": f'=SPARKLINE({{{data["Spark"]}}}, {{"charttype","line";"linewidth",2;"color","blue"}})',
            "RS": rs, "Res": f"{res_map.get(ind, 0)}隻", "ADR": f"{round(data['ADR'], 2)}%", "Vol": f"{round(data['VR'], 2)}x",
            "Mkt": f"{round(info.get('marketCap', 0)/1e9, 1)}B ", "Price": f"${round(data['P'], 2)}", "1D": f"{data['1D']*100:+.2f}%",
            "R20": f"{round(data['R20']*100, 2)}%", "R60": f"{round(data['R60']*100, 2)}%", "R120": f"{round(data['R120']*100, 2)}%",
            "VP": f"${round(data['H60']*0.95, 1)}(突)" if data['P'] > data['H60']*0.95 else f"${round(data['H60'], 1)}(壓)"
        })

    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_15, s_cnt, i_cnt =[], {}, {}
    for r in all_cands:
        if s_cnt.get(r['Sector'], 0) >= 4 or i_cnt.get(r['Industry'], 0) >= 2: continue
        top_15.append(r)
        s_cnt[r['Sector']] = s_cnt.get(r['Sector'], 0) + 1
        i_cnt[r['Industry']] = i_cnt.get(r['Industry'], 0) + 1
        if len(top_15) >= 15: break

    # 5. SPY Put 對沖 (使用現貨判定警報)
    target_date = datetime.datetime.now() + datetime.timedelta(days=90)
    hedge_ticker = f"🛡️ SPY {target_date.strftime('%b').upper()} 17 '{target_date.strftime('%y')} {int((curr_spy * 0.95) / 5) * 5} Put"
    hedge_action = "🚨 建議對沖  " if vix_spot > 19.5 or curr_spy < ma20_spy else "💤 暫無風險  "
    hedge_row =[hedge_ticker, "黑天鵝保險", "N/A", hedge_action, "VIX 現貨指引", "-", "-", "-", "-", "-", "-", "-", "-", "-", f"${round(curr_spy, 2)}", "-", "-", "-", "✅ 保底", "-", update_time]

    # 6. 輸出 (表頭顯示雙 VIX)
    headers =["Ticker", "Industry", "Score", "Action", "Msg標籤", "From 2025-12-31", "60日趨勢(圖)", "REL20", "REL60", "REL120", "RS_Rank", "行業共振", "ADR", "量比", "價格", "1D%", "MktCap", "籌碼峰", "Options", "大盤建議", "更新時間"]
    us_breadth = (above_50ma / total_valid * 100) if total_valid > 0 else 0
    
    # 💡 在表頭同時顯示現貨(真實天氣)與期貨(預期)
    m_status = f"天气:{weather}|共振:{len(perfect_tickers)}隻|全美宽度:{us_breadth:.1f}%|現貨VIX:{round(vix_spot,1)}|期貨VIX:{round(vix_fut,1)}|{macro_text}"
    row1 =[f"SuperGrowth V73 Pro Radar", f"大盤與宏觀: {m_status}", ""] + [""] * 18
    
    matrix = [row1, headers]
    for i, r in enumerate(top_15):
        matrix.append([f"👑 {r['Ticker']}" if i < 3 else r['Ticker'], r['Industry'], f"{round(r['Score'], 1)} ", r['Action'], r['Msg'], f"{round(r['YTD']*100, 2)}%", r['Trend'], r['R20'], r['R60'], r['R120'], f"{round(r['RS'], 1)} ", r['Res'], r['ADR'], r['Vol'], r['Price'], r['1D'], r['Mkt'], r['VP'], "🔥Call" if r['RS']>92 else "N/A", "✅ 持有", update_time])
    matrix.append(hedge_row)

    requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)

if __name__ == "__main__":
    run_super_growth_v73()
