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
# 1. 系統配置中心 (V102 宏觀對沖 & 防禦輪動版)
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"
TARGET_SHEET = "HK_Super"

PORTFOLIO_CAPITAL = 1_000_000  
TARGET_POSITIONS = 10
CAPITAL_PER_STOCK = PORTFOLIO_CAPITAL / TARGET_POSITIONS

# 港股核心資產池 (加入更多防禦型消費、醫藥與大宗商品)
GURU_LIST_HK = [
    "0700.HK", "9988.HK", "3690.HK", "1810.HK", "1211.HK", "2015.HK", "9868.HK", "9866.HK", 
    "0981.HK", "1347.HK", "0285.HK", "6618.HK", "9999.HK", "0883.HK", "0857.HK", "0386.HK",
    "0941.HK", "0762.HK", "0728.HK", "1088.HK", "1928.HK", "2020.HK", "6690.HK", "6862.HK",
    "2318.HK", "0388.HK", "1299.HK", "0005.HK", "0011.HK", "2382.HK", "0293.HK", "1024.HK",
    "0868.HK", "3800.HK", "2899.HK", "3993.HK", "0020.HK", "1929.HK", "6049.HK", "0772.HK",
    "1516.HK", "2269.HK", "2359.HK", "6608.HK", "9961.HK", "0268.HK", "0175.HK", "9618.HK",
    "9888.HK", "0992.HK", "1093.HK", "1177.HK", "2331.HK", "0322.HK", "0522.HK", "0836.HK",
    "0669.HK", "0151.HK", "6606.HK", "9992.HK", "9633.HK", "0867.HK", "0316.HK", "1997.HK",
    "0293.HK", "0881.HK", "2313.HK", "0104.HK" # 新增國泰航空(DAL對標), 康師傅(MNST對標), 申洲, 中國燃氣
]
EXCLUDED = ['Banks', 'Real Estate', 'REIT'] # 移除 Utilities 的排除，因為現在需要防禦

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
            return t, {
                'sector': str(info.get('sector', 'Unknown')),
                'industry': str(info.get('industry', 'Unknown')),
                'marketCap': info.get('marketCap', 0),
                'returnOnEquity': info.get('returnOnEquity', 0),
                'revenueGrowth': info.get('revenueGrowth', 0),
                'operatingMargins': info.get('operatingMargins', 0),
                'dividendYield': info.get('dividendYield', 0) # 引入股息率作為防禦指標
            }
        except: time.sleep(0.5)
    return t, {}

# ==========================================
# 3. 核心量化模型 V102
# ==========================================
def run_super_growth_hk_v102():
    update_time = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
    universe = list(set(GURU_LIST_HK))
    print("\n" + "="*60)
    print(f"🚀 [港股超級成長 V102] 啟動 | 宏觀對沖 (-MES機制) & 防守輪動")

    # --- 核心：大盤健康度偵測 (對標 MES 放空決策) ---
    try:
        m_data = yf.download(["2800.HK", "^VHSI"], period="1y", progress=False, threads=False)['Close'].ffill()
        hsi_c = m_data['2800.HK'].dropna()
        curr_hsi = float(hsi_c.iloc[-1])
        hsi_20ma = float(hsi_c.tail(20).mean())
        hsi_50ma = float(hsi_c.tail(50).mean())
        vhsi_val = float(m_data['^VHSI'].dropna().iloc[-1]) if '^VHSI' in m_data else 20.0
        
        # 判定大盤趨勢
        if curr_hsi < hsi_50ma or vhsi_val > 28.0:
            market_regime = "BEAR" # 熊市/崩盤風險
            hedge_msg = "🚨 強烈對沖 (對標 -MES): 建議買入 7300.HK (反向一倍) 或 7500.HK (反向兩倍) 覆蓋 50% 以上多頭倉位"
        elif curr_hsi < hsi_20ma:
            market_regime = "CORRECTION" # 回調期
            hedge_msg = "⚠️ 輕度對沖: 建議買入 7300.HK 對沖 20% 倉位，或提高現金水位"
        else:
            market_regime = "BULL"
            hedge_msg = "✅ 大盤多頭安全，無須放空對沖"
    except:
        market_regime, hedge_msg, vhsi_val = "BULL", "✅ 數據受限，假設安全", 20.0

    print(f"📊 當前市場狀態: {market_regime} | VHSI: {round(vhsi_val, 1)}")

    # --- 技術面掃描 ---
    hist_all = yf.download(universe, period="1y", progress=False, threads=False)['Close']
    tech_pool = {}
    for t in universe:
        if t not in hist_all.columns: continue
        c = hist_all[t].dropna()
        if len(c) < 150: continue
        
        p = float(c.iloc[-1])
        m20, m50, m200 = float(c.tail(20).mean()), float(c.tail(50).mean()), float(c.tail(200).mean())
        
        if p < m50: continue # 個股依然遵守 50MA 防守鐵律

        ema20 = float(c.ewm(span=20, adjust=False).mean().iloc[-1])
        dist_20ema = ((p - ema20) / ema20) * 100 

        tech_pool[t] = {
            "P": p, "RS_Raw": (get_ret(c, 21)*0.4) + (get_ret(c, 63)*0.4) + (get_ret(c, 126)*0.2),
            "EMA20": ema20, "Dist20EMA": dist_20ema, "Trend_Perfect": p > m20 > m50 > m200,
            "Spark": ",".join([str(round(val, 2)) for val in c.tail(60).tolist()])
        }

    if not tech_pool: return

    rs_ranks = (pd.Series({t: d['RS_Raw'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()

    # --- 動態 RS 門檻 (防守輪動邏輯) ---
    # 如果大盤轉弱，稍微放寬 RS 要求 (例如降至 55)，以便容納漲得慢但抗跌的消費/高息防禦股
    rs_threshold = 65 if market_regime == "BULL" else 55
    filtered_tech_pool = {t: d for t, d in tech_pool.items() if rs_ranks.get(t, 0) >= rs_threshold}

    print(f"⏳ 拉取基本面 (剩餘 {len(filtered_tech_pool)} 檔標的)...")
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
        div_yield = (info.get('dividendYield') or 0) * 100
        
        # 評分系統加入「防守屬性 (股息/大眾消費)」
        fund_score = (40 if rule_of_40 > 40 else (20 if rule_of_40 > 20 else 0)) + \
                     (30 if roe > 15 else (15 if roe > 8 else 0))
        
        # 如果大盤不好，高股息/防禦股加分 (對標大神的 MNST, ADM)
        is_defensive = any(d in sec for d in ['Consumer Defensive', 'Healthcare', 'Utilities', 'Energy'])
        if market_regime != "BULL":
            if div_yield > 4.0: fund_score += 20
            if is_defensive: fund_score += 15

        rs = rs_ranks.get(t, 0)
        tech_score = rs * 0.5 
        if data['Trend_Perfect']: tech_score += 10
        total_score = fund_score + tech_score
        
        dist = data['Dist20EMA']
        if -1.5 <= dist <= 2.5:
            action = "🎯 20MA企穩" 
            total_score *= 1.25 
        elif dist > 2.5:
            action = "🚀 多頭延續"
        elif dist < -3.0:
            action = "⚠️ 走勢轉弱"
            total_score *= 0.6 
        else:
            action = "🔄 震盪整理"

        price = data['P']
        raw_shares = CAPITAL_PER_STOCK / price
        suggested_shares = max(100, round(raw_shares / 100) * 100)
        actual_alloc = (suggested_shares * price) / PORTFOLIO_CAPITAL * 100

        all_cands.append({
            "Ticker": t, "Sector": sec, "Industry": ind[:10], "Score": total_score, "Action": action, 
            "Rule40": f"{round(rule_of_40, 1)}", "ROE": f"{round(roe, 1)}%", "Div": f"{round(div_yield, 1)}%",
            "DistEMA": f"{round(dist, 1)}%", "Price": f"HK${round(price, 2)}",
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
    
    # 簡化版表頭
    headers = ["代號", "板塊", "評分", "60日走勢", "操盤指令", "Rule 40", "股息防守", "乖離率", "建議股數", "資金佔比", "市價", "RS強度", "更新時間"]
    
    # 最底下強制插入「宏觀對沖」專屬行
    hedge_row = ["🛡️ 宏觀對沖", "放空指令", "-", "-", hedge_msg, "-", "-", "-", "-", "-", "-", "-", update_time]
    
    m_status = f"大盤狀態: {market_regime} | 總資金: 100萬 | 支援防禦股輪動與反向對沖"
    matrix = [[f"V102 宏觀對沖版", m_status, ""] + [""] * 10, headers]
    
    for i, r in enumerate(top_10):
        matrix.append([
            f"👑 {r['Ticker']}" if i < 3 else r['Ticker'], r['Industry'], f"{round(r['Score'], 1)}", 
            r['Trend'], r['Action'], r['Rule40'], r['Div'], r['DistEMA'], 
            r['Shares'], r['Alloc'], r['Price'], r['RS'], update_time
        ])
    
    # 寫入最後兩行做強烈提示
    matrix.append(["-" * 10, "-" * 10, "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-"])
    matrix.append(hedge_row)

    print("📤 推送 V102 策略數據至 Google Sheets...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200: print("✅ V102 數據推送成功！")
    else: print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_super_growth_hk_v102()
