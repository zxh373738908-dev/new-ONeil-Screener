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
# 1. 系統配置中心 (V99 機構級等權重配置)
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"
TARGET_SHEET = "HK_Super"

# 模擬總資金 (港幣)，用於等權重倉位計算
PORTFOLIO_CAPITAL = 1_000_000  
TARGET_POSITIONS = 10
CAPITAL_PER_STOCK = PORTFOLIO_CAPITAL / TARGET_POSITIONS

# 港股核心資產池 (排除傳統重資產與高負債)
GURU_LIST_HK = [
    "0700.HK", "9988.HK", "3690.HK", "1810.HK", "1211.HK", "2015.HK", "9868.HK", "9866.HK", 
    "0981.HK", "1347.HK", "0285.HK", "6618.HK", "9999.HK", "0883.HK", "0857.HK", "0386.HK",
    "0941.HK", "0762.HK", "0728.HK", "1088.HK", "1928.HK", "2020.HK", "6690.HK", "6862.HK",
    "2318.HK", "0388.HK", "1299.HK", "0005.HK", "0011.HK", "2382.HK", "0293.HK", "1024.HK",
    "0868.HK", "3800.HK", "2899.HK", "3993.HK", "0020.HK", "1929.HK", "6049.HK", "0772.HK",
    "1516.HK", "2269.HK", "2359.HK", "6608.HK", "9961.HK", "0268.HK", "0175.HK", "9618.HK",
    "9888.HK", "0992.HK", "1093.HK", "1177.HK", "2331.HK", "0322.HK", "0522.HK", "0836.HK",
    "0669.HK", "0151.HK", "6606.HK", "9992.HK", "9633.HK", "0867.HK", "0316.HK", "1997.HK"
]
EXCLUDED = ['Banks', 'Real Estate', 'REIT', 'Utilities']

def get_ret(series, days):
    if series is None or len(series) < days + 1: return 0.0
    val = float(series.iloc[-(days+1)])
    return (float(series.iloc[-1]) / val) - 1 if val != 0 else 0.0

def fetch_info_hk(t):
    ticker = yf.Ticker(t)
    for i in range(2):
        try:
            time.sleep(random.uniform(0.1, 0.3))
            info = ticker.info
            # 確保抓取估值與獲利能力數據
            return t, {
                'sector': str(info.get('sector', 'Unknown')),
                'industry': str(info.get('industry', 'Unknown')),
                'marketCap': info.get('marketCap', 0),
                'returnOnEquity': info.get('returnOnEquity', 0),
                'revenueGrowth': info.get('revenueGrowth', 0),
                'operatingMargins': info.get('operatingMargins', 0)
            }
        except: time.sleep(0.5)
    return t, {}

# ==========================================
# 3. 核心量化模型 V99 機構級
# ==========================================
def run_super_growth_hk_v99():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = list(set(GURU_LIST_HK))
    print("\n" + "="*60)
    print(f"🚀 [港股超級成長股 V99 機構等權重版] 啟動 | Rule of 40 & 20EMA 偵測")

    # 1. 宏觀與大盤保護機制
    try:
        m_data = yf.download(["2800.HK", "^VHSI"], period="1y", progress=False, threads=False)['Close'].ffill()
        hsi = m_data['2800.HK'].dropna()
        curr_hsi = float(hsi.iloc[-1])
        vhsi_val = float(m_data['^VHSI'].dropna().iloc[-1]) if '^VHSI' in m_data else 20.0
    except:
        curr_hsi, vhsi_val = 20.0, 20.0

    # 2. 技術面拉取 (動能與 20EMA 乖離)
    print("⏳ 正在掃描港股技術結構與乖離率...")
    hist_all = yf.download(universe, period="1y", progress=False, threads=False)['Close']
    
    tech_pool = {}
    for t in universe:
        if t not in hist_all.columns: continue
        c = hist_all[t].dropna()
        if len(c) < 150: continue
        
        p = float(c.iloc[-1])
        m20, m50, m200 = float(c.tail(20).mean()), float(c.tail(50).mean()), float(c.tail(200).mean())
        
        # 指數移動平均線 20EMA (大神買點核心)
        ema20 = float(c.ewm(span=20, adjust=False).mean().iloc[-1])
        dist_20ema = ((p - ema20) / ema20) * 100 
        
        # 嚴格基礎過濾：必須在 50MA 之上，否則直接淘汰
        if p < m50: continue 

        tech_pool[t] = {
            "P": p,
            "RS_Raw": (get_ret(c, 21)*0.4) + (get_ret(c, 63)*0.4) + (get_ret(c, 126)*0.2),
            "EMA20": ema20,
            "Dist20EMA": dist_20ema,
            "Trend_Perfect": p > m20 > m50 > m200,
            "Spark": ",".join([str(round(val, 2)) for val in c.tail(60).tolist()])
        }

    # 3. 獲取機構級基本面 (Rule of 40 & ROE)
    print("⏳ 正在拉取基本面數據 (計算 Rule of 40 與護城河 ROE)...")
    infos = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        for t, info in executor.map(fetch_info_hk, list(tech_pool.keys())):
            if info: infos[t] = info

    # 4. 深度打分與策略判定
    rs_ranks = (pd.Series({t: d['RS_Raw'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()
    all_cands = []
    
    for t, data in tech_pool.items():
        info = infos.get(t, {})
        sec, ind = info.get('sector'), info.get('industry')
        if any(ex.lower() in ind.lower() for ex in EXCLUDED): continue
        
        # --- 基本面得分引擎 ---
        roe = (info.get('returnOnEquity') or 0) * 100
        rev_g = (info.get('revenueGrowth') or 0) * 100
        op_m = (info.get('operatingMargins') or 0) * 100
        
        # 華爾街軟體/高毛利股估值法：Rule of 40
        rule_of_40 = rev_g + op_m
        
        fund_score = 0
        if rule_of_40 > 40: fund_score += 40
        elif rule_of_40 > 20: fund_score += 20
        
        if roe > 15: fund_score += 30
        elif roe > 8: fund_score += 15

        # --- 技術與動能得分 ---
        rs = rs_ranks.get(t, 0)
        tech_score = rs * 0.4 # RS 動能佔比 40%
        if data['Trend_Perfect']: tech_score += 10
        
        # 總分計算
        total_score = fund_score + tech_score
        
        # --- 大神核心買點邏輯 (基於 20EMA 乖離) ---
        dist = data['Dist20EMA']
        if -3.0 <= dist <= 1.5:
            action = "🎯 均線狙擊"
            total_score *= 1.2 # 在完美買點區間給予加分
        elif dist > 1.5:
            action = "👀 觀望(乖離)"
        else:
            action = "🛡️ 抱緊防禦"

        # --- 倉位管理 (等權重計算器) ---
        price = data['P']
        raw_shares = CAPITAL_PER_STOCK / price
        # 港股約整至 100 股為一手 (模擬)
        suggested_shares = max(100, round(raw_shares / 100) * 100)
        actual_alloc = (suggested_shares * price) / PORTFOLIO_CAPITAL * 100

        all_cands.append({
            "Ticker": t, "Sector": sec, "Industry": ind[:12], 
            "Score": total_score, "Action": action, 
            "Rule40": f"{round(rule_of_40, 1)}", "ROE": f"{round(roe, 1)}%",
            "DistEMA": f"{round(dist, 1)}%", "Price": f"HK${round(price, 2)}",
            "Shares": f"{suggested_shares} 股", "Alloc": f"{round(actual_alloc, 1)}%",
            "Trend": f'=SPARKLINE({{{data["Spark"]}}}, {{"charttype","line";"color","red"}})',
            "RS": round(rs, 1)
        })

    # 5. 精煉 Top 10 (嚴格板塊分散)
    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_10, sec_cnt = [], {}
    
    for r in all_cands:
        s = r['Sector']
        if sec_cnt.get(s, 0) >= 3: continue # 單一板塊絕對不超過 3 檔
        top_10.append(r)
        sec_cnt[s] = sec_cnt.get(s, 0) + 1
        if len(top_10) >= TARGET_POSITIONS: break

    # 6. 大盤對沖保護
    hedge_action = "🚨 買入對沖" if vhsi_val > 25.0 else "💤 暫無風險"
    hedge_row = ["🛡️ 2800.HK Tracker", "大盤保險", "-", "-", hedge_action, "-", "-", "-", "-", "-", "-", "-", "-", "-", update_time]

    # 7. 輸出至 Google Sheets (全新表頭)
    headers = ["Ticker", "Industry", "綜合評分", "趨勢(60d)", "操盤指令", "Rule of 40\n(營收+利潤率)", "ROE\n(護城河)", "20EMA乖離\n(買點判定)", "建議股數\n(等權重)", "資金佔比", "目前股價", "RS_Rank", "-", "-", "更新時間"]
    
    m_status = f"VHSI波幅: {round(vhsi_val,1)} | 總模擬資金: 100萬 HKD | 每檔配置: ~10%"
    matrix = [[f"V99 機構等權重配置", m_status, ""] + [""] * 12, headers]
    
    for i, r in enumerate(top_10):
        matrix.append([
            f"👑 {r['Ticker']}" if i < 3 else r['Ticker'], r['Industry'], f"{round(r['Score'], 1)}", 
            r['Trend'], r['Action'], r['Rule40'], r['ROE'], r['DistEMA'], 
            r['Shares'], r['Alloc'], r['Price'], r['RS'], "-", "-", update_time
        ])
    matrix.append(hedge_row)

    print("📤 正在推送 V99 實盤指令到 Google Sheets...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200: print("✅ V99 數據推送成功！")
    else: print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_super_growth_hk_v99()
