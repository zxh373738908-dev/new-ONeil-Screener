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
# 1. 系統配置中心 (V105 量價齊升 & 動能衰竭版)
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"
TARGET_SHEET = "HK_Super"

PORTFOLIO_CAPITAL = 1_000_000  
TARGET_POSITIONS = 10
CAPITAL_PER_STOCK = PORTFOLIO_CAPITAL / TARGET_POSITIONS

# 根據大神的 Risk-On 切換，微調港股池 (增加半導體、原物料、消費復甦)
GURU_LIST_HK = [
    "0700.HK", "9988.HK", "3690.HK", "1810.HK", "1211.HK", "2015.HK", "9868.HK", "9866.HK", 
    "0981.HK", "1347.HK", "0285.HK", "6618.HK", "9999.HK", "0883.HK", "0857.HK", "0386.HK",
    "0941.HK", "0762.HK", "0728.HK", "1088.HK", "1928.HK", "2020.HK", "6690.HK", "6862.HK",
    "2318.HK", "0388.HK", "1299.HK", "0005.HK", "0011.HK", "2382.HK", "0293.HK", "1024.HK",
    "0868.HK", "3800.HK", "2899.HK", "3993.HK", "0020.HK", "1929.HK", "6049.HK", "0772.HK",
    "1516.HK", "2269.HK", "2359.HK", "6608.HK", "9961.HK", "0268.HK", "0175.HK", "9618.HK",
    "9888.HK", "0992.HK", "1093.HK", "1177.HK", "2331.HK", "0322.HK", "0522.HK", "0836.HK",
    "0669.HK", "0151.HK", "6606.HK", "9992.HK", "9633.HK", "0867.HK", "0316.HK", "1997.HK",
    "0293.HK", "0881.HK", "2313.HK", "0780.HK", "2899.HK" # 0780(同程旅行-對標VIK), 2899(紫金-對標ATI)
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
                'operatingMargins': info.get('operatingMargins', 0),
                'dividendYield': info.get('dividendYield', 0)
            }
        except: time.sleep(0.5)
    return t, {}

# ==========================================
# 3. 核心量化模型 V105
# ==========================================
def run_super_growth_hk_v105():
    update_time = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
    universe = list(set(GURU_LIST_HK))
    print("\n" + "="*60)
    print(f"🚀 [港股超級成長 V105] 啟動 | 放量突破偵測 & 動能衰竭(移動停利)機制")

    # 1. 宏觀對沖引擎
    market_regime = "BULL"
    hedge_msg = "✅ 大盤多頭安全，切換進攻模式"
    try:
        hsi_data = yf.download("2800.HK", period="1y", progress=False, threads=False)['Close']
        if not hsi_data.empty:
            hsi_c = hsi_data.dropna()
            curr_hsi = float(hsi_c.iloc[-1])
            hsi_20ma, hsi_50ma = float(hsi_c.tail(20).mean()), float(hsi_c.tail(50).mean())
            
            if curr_hsi < hsi_50ma:
                market_regime = "BEAR"
                hedge_msg = "🚨 強烈對沖 (對標 -MES): 買入 7300.HK 覆蓋 50% 倉位"
            elif curr_hsi < hsi_20ma:
                market_regime = "CORRECTION"
                hedge_msg = "⚠️ 輕度對沖: 建議買入 7300.HK 對沖 20% 倉位"
    except: pass

    # 2. 技術面與量能(Volume)雙重掃描
    print("⏳ 掃描技術面結構與機構量能 (Volume Ratio)...")
    hist_all = yf.download(universe, period="1y", progress=False, threads=False)
    close_df = hist_all['Close']
    vol_df = hist_all['Volume']
    
    tech_pool = {}
    for t in universe:
        if t not in close_df.columns or t not in vol_df.columns: continue
        c, v = close_df[t].dropna(), vol_df[t].dropna()
        if len(c) < 150: continue
        
        p = float(c.iloc[-1])
        m20, m50, m200 = float(c.tail(20).mean()), float(c.tail(50).mean()), float(c.tail(200).mean())
        
        # 流動性過濾
        avg_vol_10 = float(v.tail(10).mean())
        if p < 1.0 or (avg_vol_10 * p) < 10_000_000: continue 
        if p < m50: continue 

        ema20 = float(c.ewm(span=20, adjust=False).mean().iloc[-1])
        dist_20ema = ((p - ema20) / ema20) * 100 

        # 🎯 V105 量比計算 (Volume Ratio: 當日量 / 50日均量)
        avg_vol_50 = float(v.tail(50).mean())
        vr = float(v.iloc[-1]) / avg_vol_50 if avg_vol_50 > 0 else 1.0

        tech_pool[t] = {
            "P": p, "RS_Raw": (get_ret(c, 21)*0.4) + (get_ret(c, 63)*0.4) + (get_ret(c, 126)*0.2),
            "EMA20": ema20, "Dist20EMA": dist_20ema, "Trend_Perfect": p > m20 > m50 > m200,
            "VR": vr, "Spark": ",".join([str(round(val, 2)) for val in c.tail(60).tolist()])
        }

    if not tech_pool: 
        print("⚠️ 當前無符合標的。")
    else:
        rs_ranks = (pd.Series({t: d['RS_Raw'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()
        rs_threshold = 65 if market_regime == "BULL" else 55
        filtered_tech_pool = {t: d for t, d in tech_pool.items() if rs_ranks.get(t, 0) >= rs_threshold}

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
            
            raw_div = info.get('dividendYield') or 0
            div_yield = raw_div * 100 if raw_div < 0.3 else raw_div
            
            fund_score = (40 if rule_of_40 > 40 else (20 if rule_of_40 > 20 else 0)) + \
                         (30 if roe > 15 else (15 if roe > 8 else 0))
            
            is_defensive = any(d in sec for d in ['Consumer Defensive', 'Healthcare', 'Utilities'])
            if market_regime != "BULL":
                if div_yield > 4.0: fund_score += 20
                if is_defensive: fund_score += 15

            rs = rs_ranks.get(t, 0)
            vr = data['VR']
            dist = data['Dist20EMA']
            
            tech_score = rs * 0.5 
            if data['Trend_Perfect']: tech_score += 10
            
            # 🎯 V105 量能動態加分引擎
            if vr > 1.5 and dist > 0: tech_score += 20  # 機構放量拉升加分
            if vr < 0.7 and -2 <= dist <= 2: tech_score += 15 # 量縮極致洗盤加分
            
            total_score = fund_score + tech_score
            
            # 🎯 V105 終極操盤指令 (結合量價與停損/停利邏輯)
            if dist > 15.0:
                action = "⚠️ 乖離過熱" # 漲太多了，提醒不要追高，準備移動停利
            elif 0 <= dist <= 5.0 and vr >= 1.5:
                action = "🔥 放量突破" # 完美復刻 MU 買點
                total_score *= 1.3
            elif -2.0 <= dist <= 2.5 and vr < 0.8:
                action = "🎯 量縮企穩" # 完美復刻潛伏買點
                total_score *= 1.2
            elif dist > 2.5:
                action = "🚀 多頭延續" # 抱著不要動
            elif dist < -3.0:
                action = "✂️ 跌破/停損" # 跌破 20EMA 太深，完美復刻 ROKU 砍倉邏輯
                total_score *= 0.5 # 暴力扣分，將其踢出名單
            else:
                action = "🔄 震盪整理"

            price = data['P']
            raw_shares = CAPITAL_PER_STOCK / price
            suggested_shares = max(100, round(raw_shares / 100) * 100)
            actual_alloc = (suggested_shares * price) / PORTFOLIO_CAPITAL * 100

            all_cands.append({
                "Ticker": t, "Sector": sec, "Industry": ind[:10], "Score": total_score, "Action": action, 
                "Rule40": f"{round(rule_of_40, 1)}", "VR": f"{round(vr, 2)}x", "DistEMA": f"{round(dist, 1)}%", 
                "Price": f"HK${round(price, 2)}", "Shares": f"{suggested_shares} 股", "Alloc": f"{round(actual_alloc, 1)}%",
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
    
    # 表頭將「股息」換成更關鍵的「量比(VR)」，因為切換回攻擊模式了
    headers = ["股票代號", "行業板塊", "系統評分", "60日走勢", "操盤指令(移動停利/損)", "Rule 40", "機構量比", "20EMA乖離", "建議股數", "資金佔比", "市價", "動能 RS", "更新時間"]
    hedge_row = ["🛡️ 宏觀對沖", "放空指令", "-", "-", hedge_msg, "-", "-", "-", "-", "-", "-", "-", update_time]
    
    m_status = f"大盤: {market_regime} | 新增放量突破(VR) & 移動停利機制"
    matrix = [[f"V105 機構動能版", m_status, ""] + [""] * 10, headers]
    
    if tech_pool:
        for i, r in enumerate(top_10):
            matrix.append([
                f"👑 {r['Ticker']}" if i < 3 else r['Ticker'], r['Industry'], f"{round(r['Score'], 1)}", 
                r['Trend'], r['Action'], r['Rule40'], r['VR'], r['DistEMA'], 
                r['Shares'], r['Alloc'], r['Price'], r['RS'], update_time
            ])
    
    matrix.append(["-" * 10] * 13)
    matrix.append(hedge_row)

    print("📤 推送 V105 策略數據至 Google Sheets...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200: print("✅ V105 數據推送成功！")
    else: print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_super_growth_hk_v105()
