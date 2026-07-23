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
# 1. 系統配置中心 (V110 機構再平衡計算機版)
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"
TARGET_SHEET = "HK_Super"

# 🎯 完全復刻大神截圖中的資金管理邏輯
PORTFOLIO_CAPITAL = 1_000_000         # 總資金 (帳戶資本)
CASH_RESERVE_PCT = 0.05               # 備用金比例 5%
TARGET_POSITIONS = 10                 # 股票數量 10 檔

AVAILABLE_CAPITAL = PORTFOLIO_CAPITAL * (1 - CASH_RESERVE_PCT)
TARGET_VALUE_PER_STOCK = AVAILABLE_CAPITAL / TARGET_POSITIONS  # 應持有市值

# 🚨 解禁所有板塊限制 (迎合大神的價值/週期輪動)
GURU_LIST_HK = [
    "0700.HK", "9988.HK", "3690.HK", "1810.HK", "1211.HK", "2015.HK", "9868.HK", "9866.HK", 
    "0981.HK", "1347.HK", "0285.HK", "6618.HK", "9999.HK", "0883.HK", "0857.HK", "0386.HK", 
    "0941.HK", "0762.HK", "0728.HK", "1088.HK", "1928.HK", "2020.HK", "6690.HK", "6862.HK",
    "2318.HK", "0388.HK", "1299.HK", "2382.HK", "0293.HK", "1024.HK", "9626.HK",
    "0868.HK", "3800.HK", "2899.HK", "3993.HK", "0020.HK", "1929.HK", "6049.HK", "0772.HK", 
    "1516.HK", "2269.HK", "2359.HK", "6608.HK", "9961.HK", "0268.HK", "0175.HK", "9618.HK",
    "9888.HK", "0992.HK", "1093.HK", "1177.HK", "2331.HK", "0322.HK", "0522.HK", "0836.HK",
    "0669.HK", "0151.HK", "6606.HK", "9992.HK", "9633.HK", "0867.HK", "0316.HK", "1997.HK", # 1997.HK (地產REIT對標HST)
    "0293.HK", "0881.HK", "2313.HK", "0780.HK", "1088.HK", "1919.HK", 
    "1072.HK", "1133.HK", "0005.HK", "2618.HK" # 0005.HK(銀行對標STT), 2618.HK(物流對標JBHT)
]

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
# 3. 核心量化模型 V110
# ==========================================
def run_super_growth_hk_v110():
    update_time = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
    universe = list(set(GURU_LIST_HK))
    print("\n" + "="*60)
    print(f"🚀 [港股 動量組合 V110] 啟動 | 風格大輪動 & 調倉計算機")

    market_regime = "BULL (🚀積極進攻)"
    hedge_msg = "✅ 大盤多頭安全，無須對沖"
    
    try:
        m_data = yf.download(["2800.HK"], period="6mo", progress=False, threads=False)['Close'].ffill()
        hsi_c = m_data['2800.HK'].dropna()
        if float(hsi_c.iloc[-1]) < float(hsi_c.tail(50).mean()):
            market_regime = "BEAR (🚨防禦對沖)"
            hedge_msg = "🚨 強烈對沖 (對標 -MES): 買入 7300.HK 覆蓋 50% 倉位"
    except: pass

    print("⏳ 掃描個股動能、高波幅特徵(ADR) 與 乖離率...")
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

        hsi_ret_20 = get_ret(hsi_c, 20) if 'hsi_c' in locals() else 0
        hsi_ret_60 = get_ret(hsi_c, 60) if 'hsi_c' in locals() else 0
        rel_20 = (get_ret(c, 20) - hsi_ret_20) * 100
        rel_60 = (get_ret(c, 60) - hsi_ret_60) * 100
        
        adr = float(((high_df[t].tail(14) - low_df[t].tail(14)) / low_df[t].tail(14)).mean() * 100)
        ret_5 = get_ret(c, 5) * 100

        tech_pool[t] = {
            "P": p, "RS_Raw": (get_ret(c, 21)*0.4) + (get_ret(c, 63)*0.4) + (get_ret(c, 126)*0.2),
            "EMA20": ema20, "Dist20EMA": dist_20ema, "VR": vr, "ADR": adr,
            "REL20": rel_20, "REL60": rel_60, "Ret5": ret_5,
            "Spark": ",".join([str(round(val, 2)) for val in c.tail(60).tolist()])
        }

    if not tech_pool: 
        print("⚠️ 查無符合標的。")
        return

    rs_ranks = (pd.Series({t: d['RS_Raw'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()
    filtered_tech_pool = {t: d for t, d in tech_pool.items() if rs_ranks.get(t, 0) >= 65}

    print(f"⏳ 拉取基本面 (解禁全板塊)...")
    infos = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        for t, info in executor.map(fetch_info_hk, list(filtered_tech_pool.keys())):
            if info: infos[t] = info

    all_cands = []
    for t, data in filtered_tech_pool.items():
        info = infos.get(t, {})
        sec, ind = info.get('sector'), info.get('industry')
        
        roe = (info.get('returnOnEquity') or 0) * 100
        rule_of_40 = (info.get('revenueGrowth') or 0) * 100 + (info.get('operatingMargins') or 0) * 100
        
        fund_score = (40 if rule_of_40 > 40 else (20 if rule_of_40 > 20 else 0)) + \
                     (30 if roe > 15 else (15 if roe > 8 else 0))
        
        rs, dist, vr, rel20, ret5, adr = rs_ranks.get(t, 0), data['Dist20EMA'], data['VR'], data['REL20'], data['Ret5'], data['ADR']
        
        tech_score = rs * 0.5 
        if vr > 1.5 and dist > 0: tech_score += 15 
        total_score = fund_score + tech_score
        
        # 🎯 操盤指令判定
        if adr >= 4.5 and rel20 >= 5.0 and 0 <= dist <= 5.0 and vr > 1.2:
            action = f"🚀核爆({dist:+.1f}%)"
            total_score *= 1.4 
        elif ret5 > 4.0 and 0 <= dist <= 3.0: 
            action = f"🦅破底翻({dist:+.1f}%)"
            total_score *= 1.35 
        elif dist < -3.0:
            action = f"✂️破線停損({dist:+.1f}%)"
            total_score *= 0.3
        elif rel20 < -3.0:
            action = f"✂️滯漲剔除({dist:+.1f}%)"
            total_score *= 0.4
        elif 0 <= dist <= 3.0:
            action = f"🎯狙擊({dist:+.1f}%)" if vr > 1.2 else f"🎯加倉({dist:+.1f}%)"
            total_score *= 1.2
        elif -3.0 <= dist < 0:
            action = f"🎯加倉({dist:+.1f}%)"
            total_score *= 1.2
        elif dist > 8.0:
            action = f"👀觀望({dist:+.1f}%)" 
        else:
            action = f"🛡️續抱({dist:+.1f}%)"

        # 🎯 大神公式：應持有股份數 = 應持有市值 / 最新收盤價 (港股約整至100股)
        price = data['P']
        raw_shares = TARGET_VALUE_PER_STOCK / price
        target_shares = max(100, round(raw_shares / 100) * 100)

        all_cands.append({
            "Ticker": t, "Sector": sec, "Industry": ind[:10], "Score": total_score, "Action": action, 
            "REL20": f"{rel20:+.1f}%", "ADR": f"{round(adr, 1)}%", "VR": f"{round(vr, 2)}x", "Price": f"{round(price, 2)}",
            "TargetValue": f"{round(TARGET_VALUE_PER_STOCK, 0):,}", # 應持有市值
            "TargetShares": f"{target_shares}",                      # 應持有股份數
            "Trend": f'=SPARKLINE({{{data["Spark"]}}}, {{"charttype","line";"color","red"}})', 
            "RS": f"{round(rs, 1)} 分"
        })

    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_10, sec_cnt = [], {}
    for r in all_cands:
        s = r['Sector']
        if sec_cnt.get(s, 0) >= 4: continue # 放寬板塊容忍度至 4，適應極端抱團
        top_10.append(r)
        sec_cnt[s] = sec_cnt.get(s, 0) + 1
        if len(top_10) >= TARGET_POSITIONS: break
    
    # 🎯 輸出矩陣：完美對齊大神計算表
    header1 = [f"動量組合・調倉計算表 V110", "", "", "", "", "", "", "", "", "", "", "", "", ""]
    header2 = ["帳戶資本 (HKD)", f"{PORTFOLIO_CAPITAL:,.2f}", "", "", "", "", "", "", "", "", "", "", "", ""]
    header3 = ["備用金 5%", f"{PORTFOLIO_CAPITAL * CASH_RESERVE_PCT:,.2f}", "", "", "", "", "", "", "", "", "", "", "", ""]
    header4 = ["目標股票數量", f"{TARGET_POSITIONS}", "", "", "", "", "", "", "", "", "", "", "", ""]
    headers_col = ["最新持倉", "行業", "綜合評分", "60日走勢", "操盤指令", "現價", "應持有市值", "應持有股份數", "超額REL20", "量比(VR)", "ADR波幅", "RS動能", "-", "更新時間"]
    
    hedge_row = ["🛡️ 對沖部位", "-", "-", "-", hedge_msg, "-", "-", "-", "-", "-", "-", "-", "-", update_time]

    matrix = [header1, header2, header3, header4, [""]*14, headers_col]
    
    for i, r in enumerate(top_10):
        matrix.append([
            f"👑 {r['Ticker']}" if i < 10 else r['Ticker'], r['Industry'], f"{round(r['Score'], 1)}", 
            r['Trend'], r['Action'], r['Price'], r['TargetValue'], r['TargetShares'], r['REL20'], r['VR'], r['ADR'], r['RS'], "-", update_time
        ])

    matrix.append(["-" * 10] * 14)
    matrix.append(hedge_row) 

    print("📤 推送 V110 調倉計算表至 Google Sheets...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200: print("✅ V110 數據推送成功！")
    else: print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_super_growth_hk_v110()
