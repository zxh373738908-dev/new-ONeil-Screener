import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import requests
import warnings
import time
import random
from concurrent.futures import ThreadPoolExecutor

warnings.filterwarnings('ignore')

# ==========================================
# 1. 系統配置中心 (V106 能源輪動 & 弱勢斬首版)
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"
TARGET_SHEET = "HK_Super"

PORTFOLIO_CAPITAL = 1_000_000  
TARGET_POSITIONS = 10
CAPITAL_PER_STOCK = PORTFOLIO_CAPITAL / TARGET_POSITIONS

# 港股池 (確保三桶油、煤炭、紫金礦業等「大宗商品/能源」在列)
GURU_LIST_HK = [
    "0700.HK", "9988.HK", "3690.HK", "1810.HK", "1211.HK", "2015.HK", "9868.HK", "9866.HK", 
    "0981.HK", "1347.HK", "0285.HK", "6618.HK", "9999.HK", "0883.HK", "0857.HK", "0386.HK", # 中海油, 中石油, 中石化
    "0941.HK", "0762.HK", "0728.HK", "1088.HK", "1928.HK", "2020.HK", "6690.HK", "6862.HK",
    "2318.HK", "0388.HK", "1299.HK", "2382.HK", "0293.HK", "1024.HK",
    "0868.HK", "3800.HK", "2899.HK", "3993.HK", "0020.HK", "1929.HK", "6049.HK", "0772.HK", # 2899 紫金, 3993 洛陽鉬業
    "1516.HK", "2269.HK", "2359.HK", "6608.HK", "9961.HK", "0268.HK", "0175.HK", "9618.HK",
    "9888.HK", "0992.HK", "1093.HK", "1177.HK", "2331.HK", "0322.HK", "0522.HK", "0836.HK",
    "0669.HK", "0151.HK", "6606.HK", "9992.HK", "9633.HK", "0867.HK", "0316.HK", "1997.HK",
    "0293.HK", "0881.HK", "2313.HK", "0780.HK", "1088.HK", "1919.HK" # 1088 神華, 1919 中遠海控
]
EXCLUDED = ['Banks', 'Real Estate', 'REIT']

def get_ret(series, days):
    if series is None or len(series) < days + 1: return 0.0
    val = float(series.iloc[-(days+1)])
    return (float(series.iloc[-1]) / val) - 1 if val != 0 else 0.0

def fetch_info_hk(t):
    ticker = yf.Ticker(t)
    for i in range(2):
        try:
            time.sleep(random.uniform(0.1, 0.2))
            info = ticker.info
            return t, {
                'sector': str(info.get('sector', 'Unknown')),
                'industry': str(info.get('industry', 'Unknown')),
                'returnOnEquity': info.get('returnOnEquity', 0),
                'revenueGrowth': info.get('revenueGrowth', 0),
                'operatingMargins': info.get('operatingMargins', 0)
            }
        except: time.sleep(0.5)
    return t, {}

# ==========================================
# 3. 核心量化模型 V106
# ==========================================
def run_super_growth_hk_v106():
    update_time = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
    universe = list(set(GURU_LIST_HK))
    print("\n" + "="*60)
    print(f"🚀 [港股 Master Sniper V106] 啟動 | 能源輪動 & 弱勢斬首機制")

    # 1. 大盤與商品宏觀引擎 (判斷 Risk-On 與 能源週期)
    market_regime = "BULL (🚀積極進攻)"
    oil_trending = False
    
    try:
        # 抓取大盤與原油 (CL=F)
        m_data = yf.download(["2800.HK", "CL=F"], period="6mo", progress=False, threads=False)['Close'].ffill()
        hsi_c = m_data['2800.HK'].dropna()
        oil_c = m_data['CL=F'].dropna()
        
        curr_hsi = float(hsi_c.iloc[-1])
        if curr_hsi < float(hsi_c.tail(50).mean()):
            market_regime = "BEAR (🚨防禦對沖)"
            
        # 判斷原油是否處於多頭 (大於 50MA)
        if float(oil_c.iloc[-1]) > float(oil_c.tail(50).mean()):
            oil_trending = True
            print("🛢️ 偵測到原油/大宗商品走強，啟動【能源輪動 (Energy Rotation)】加分機制！")
    except: pass

    # 2. 技術面、相對強度 (REL) 與波幅 (ADR) 掃描
    print("⏳ 掃描個股動能、REL20 與 ADR...")
    hist_all = yf.download(universe, period="1y", progress=False, threads=False)
    close_df = hist_all['Close']
    vol_df = hist_all['Volume']
    high_df = hist_all['High']
    low_df = hist_all['Low']
    
    tech_pool = {}
    for t in universe:
        if t not in close_df.columns or t not in vol_df.columns: continue
        c, v = close_df[t].dropna(), vol_df[t].dropna()
        if len(c) < 150: continue
        
        p = float(c.iloc[-1])
        m20, m50 = float(c.tail(20).mean()), float(c.tail(50).mean())
        
        avg_vol_10 = float(v.tail(10).mean())
        if p < 1.0 or (avg_vol_10 * p) < 10_000_000: continue 
        if p < m50: continue 

        ema20 = float(c.ewm(span=20, adjust=False).mean().iloc[-1])
        dist_20ema = ((p - ema20) / ema20) * 100 
        vr = float(v.iloc[-1]) / float(v.tail(50).mean()) if float(v.tail(50).mean()) > 0 else 1.0

        # 計算 REL (相對大盤超額報酬)
        hsi_ret_20 = get_ret(hsi_c, 20) if 'hsi_c' in locals() else 0
        hsi_ret_60 = get_ret(hsi_c, 60) if 'hsi_c' in locals() else 0
        rel_20 = (get_ret(c, 20) - hsi_ret_20) * 100
        rel_60 = (get_ret(c, 60) - hsi_ret_60) * 100
        
        # 計算 ADR (14天平均波幅)
        adr = float(((high_df[t].tail(14) - low_df[t].tail(14)) / low_df[t].tail(14)).mean() * 100)

        tech_pool[t] = {
            "P": p, "RS_Raw": (get_ret(c, 21)*0.4) + (get_ret(c, 63)*0.4) + (get_ret(c, 126)*0.2),
            "EMA20": ema20, "Dist20EMA": dist_20ema, "VR": vr, "ADR": adr,
            "REL20": rel_20, "REL60": rel_60,
            "Spark": ",".join([str(round(val, 2)) for val in c.tail(60).tolist()])
        }

    if not tech_pool: 
        print("⚠️ 查無符合標的。")
        return

    rs_ranks = (pd.Series({t: d['RS_Raw'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()
    # 積極進攻模式，只篩選 RS > 65 的真正強勢股
    filtered_tech_pool = {t: d for t, d in tech_pool.items() if rs_ranks.get(t, 0) >= 65}

    print(f"⏳ 拉取基本面 (剩餘 {len(filtered_tech_pool)} 檔合規標的)...")
    infos = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        for t, info in executor.map(fetch_info_hk, list(filtered_tech_pool.keys())):
            if info: infos[t] = info

    all_cands = []
    for t, data in filtered_tech_pool.items():
        info = infos.get(t, {})
        sec, ind = info.get('sector'), info.get('industry')
        if any(ex.lower() in ind.lower() for ex in EXCLUDED): continue
        
        roe = (info.get('returnOnEquity') or 0) * 100
        rule_of_40 = (info.get('revenueGrowth') or 0) * 100 + (info.get('operatingMargins') or 0) * 100
        
        fund_score = (40 if rule_of_40 > 40 else (20 if rule_of_40 > 20 else 0)) + \
                     (30 if roe > 15 else (15 if roe > 8 else 0))
        
        # 🛢️ 能源輪動機制 (Energy Rotation)
        is_energy_metals = any(d in sec for d in ['Energy', 'Basic Materials'])
        if oil_trending and is_energy_metals:
            fund_score += 25 # 順風板塊大幅加分

        rs = rs_ranks.get(t, 0)
        dist = data['Dist20EMA']
        vr = data['VR']
        rel20 = data['REL20']
        
        tech_score = rs * 0.5 
        if vr > 1.5 and dist > 0: tech_score += 15 
        
        total_score = fund_score + tech_score
        
        # 🎯 V106 視覺化狙擊指令 (對標 V95 Master Sniper)
        # 邏輯：破線或跑輸大盤 -> 斬首 | 貼近均線 -> 狙/加 | 漲太多 -> 觀 | 穩定 -> 抱
        if dist < -3.0 or rel20 < -5.0:
            action = f"⚠️汰(破線)"
            total_score *= 0.3 # 弱勢斬首 (Weakness Purge)
        elif 0 <= dist <= 3.0:
            action = f"🎯狙(乖離{dist:.1f}%)" if vr > 1.2 else f"🎯加(乖離{dist:.1f}%)"
            total_score *= 1.2
        elif -3.0 <= dist < 0:
            action = f"🎯加(乖離{dist:.1f}%)"
            total_score *= 1.2
        elif dist > 8.0:
            action = f"👀觀(乖離{dist:.1f}%)" # 漲太多，只觀望不追
        else:
            action = f"🛡️抱(乖離{dist:.1f}%)"

        price = data['P']
        raw_shares = CAPITAL_PER_STOCK / price
        suggested_shares = max(100, round(raw_shares / 100) * 100)
        actual_alloc = (suggested_shares * price) / PORTFOLIO_CAPITAL * 100

        all_cands.append({
            "Ticker": t, "Sector": sec, "Industry": ind[:10], "Score": total_score, "Action": action, 
            "REL20": f"{round(rel20, 1)}%", "REL60": f"{round(data['REL60'], 1)}%", "ADR": f"{round(data['ADR'], 1)}%",
            "VR": f"{round(vr, 2)}x", "Price": f"HK${round(price, 2)}",
            "Shares": f"{suggested_shares} 股", "Alloc": f"{round(actual_alloc, 1)}%",
            "Trend": f'=SPARKLINE({{{data["Spark"]}}}, {{"charttype","line";"color","red"}})', "RS": round(rs, 1)
        })

    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_10, sec_cnt = [], {}
    for r in all_cands:
        s = r['Sector']
        if sec_cnt.get(s, 0) >= 3: continue 
        top_10.append(r)
        sec_cnt[s] = sec_cnt.get(s, 0) + 1
        if len(top_10) >= TARGET_POSITIONS: break
    
    # 完美對齊 V95 表頭
    headers = ["代碼", "板塊", "評分", "60日走勢", "作戰指令", "REL20", "REL60", "RS_Rank", "ADR波幅", "量比", "價格", "建議股數", "資金佔比", "更新時間"]
    
    m_status = f"更新: {update_time} | 狀態: {market_regime} | 🛢️ 能源輪動: {'ON' if oil_trending else 'OFF'} | Weakness Purge 啟動"
    matrix = [[f"Master Sniper V106 (Energy Rotation & Weakness Purge)", m_status, ""] + [""] * 11, headers]
    
    for i, r in enumerate(top_10):
        matrix.append([
            f"👑 {r['Ticker']}" if i < 10 else r['Ticker'], r['Industry'], f"{round(r['Score'], 1)}", 
            r['Trend'], r['Action'], r['REL20'], r['REL60'], r['RS'], r['ADR'], r['VR'], 
            r['Price'], r['Shares'], r['Alloc'], update_time
        ])

    print("📤 推送 V106 策略數據至 Google Sheets...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200: print("✅ V106 數據推送成功！")
    else: print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_super_growth_hk_v106()
