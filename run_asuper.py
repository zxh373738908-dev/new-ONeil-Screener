import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import requests
import warnings
import time
import random
import math
from concurrent.futures import ThreadPoolExecutor

warnings.filterwarnings('ignore')

# ==========================================
# 1. 系統配置中心 (V130 能源輪動與狙擊手版)
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"
TARGET_SHEET = "A_Super" 
PORTFOLIO_CAPITAL = 1000000  

# 🚀 V130 大神同步股票池：加入能源，剔除彩票
GURU_LIST_A =[
    # 🛢️ 新增：傳統能源/高股息/油氣基建 (對標 TRGP)
    "600938.SS", # 中國海油
    "601088.SS", # 中國神華
    "600256.SS", # 廣匯能源
    "601872.SS", # 招商輪船 (能源運輸)
    
    # 存儲/半導體 (對標 MU)
    "603986.SS", "301308.SZ", "688525.SS", 
    # 低軌衛星/通訊 (對標 IRDM)
    "601698.SS", "001270.SZ", "688292.SS", 
    # 特種金屬/軍工材料 (對標 ATI)
    "600893.SS", "600862.SS", "688122.SS", 
    # 航空/免稅/高端消費 (對標 DAL, VIK, MNST)
    "601888.SS", "601111.SS", "605499.SS",
    # 券商/高息金融 (對標 IBKR)
    "600030.SS", "300059.SZ",
    # 絕對核心老將 (對標 PWR, LLY)
    "300308.SZ", "600487.SS", "603259.SS", "600276.SS"
]

def get_universe_a(): return list(set(GURU_LIST_A))

def fetch_info_a(t):
    ticker = yf.Ticker(t)
    for i in range(2):
        try:
            time.sleep(random.uniform(0.1, 0.2))
            info = ticker.info
            if info and 'industry' in info:
                return t, {
                    'sector': str(info.get('sector', 'Unknown')),
                    'returnOnEquity': info.get('returnOnEquity', 0),
                    'dividendYield': info.get('dividendYield', 0) # V130: 引入股息率評估能源股
                }
        except: time.sleep(0.3)
    return t, {}

def get_ret(series, days):
    if series is None or len(series) < days + 1: return 0.0
    val = float(series.iloc[-(days+1)])
    return (float(series.iloc[-1]) / val) - 1 if val != 0 else 0.0

# ==========================================
# 3. 核心量化模型 V130
# ==========================================
def run_super_growth_a():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = get_universe_a()
    print("\n" + "="*65)
    print(f"🎯 [A股 Master Sniper V130] 啟動 | 載入「能源輪動」與「弱勢清洗」引擎...")

    hist_all = yf.download(universe, period="1y", progress=False, threads=False)
    if hist_all.empty: return
    close_df, vol_df = hist_all['Close'], hist_all['Volume']
    
    tech_pool = {}
    for t in universe:
        try:
            c, v = close_df[t].dropna(), vol_df[t].dropna()
            p = float(c.iloc[-1])
            if len(c) < 100 or p < 1.0: continue
            
            m20, m50 = float(c.tail(20).mean()), float(c.tail(50).mean())
            ema20 = float(c.ewm(span=20, adjust=False).mean().iloc[-1])
            dist_20ema = ((p - ema20) / ema20) * 100
            
            rs_raw = (get_ret(c, 21)*0.4) + (get_ret(c, 63)*0.4) + (get_ret(c, 126)*0.2)
            vol_50d_avg = float(v.tail(50).mean())
            is_vdu = float(v.tail(3).mean()) < (vol_50d_avg * 0.75)
            
            tech_pool[t] = {
                "P": p, "Dist20": dist_20ema, "Stop_Loss": m50,
                "RS_Raw": rs_raw, "Is_VDU": is_vdu
            }
        except: continue

    infos = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        for t, info in executor.map(fetch_info_a, list(tech_pool.keys())):
            if info: infos[t] = info

    rs_ranks = (pd.Series({t: d['RS_Raw'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()
    all_cands = []
    
    for t, data in tech_pool.items():
        info, rs = infos.get(t, {}), rs_ranks.get(t, 0)
        
        # 🔪 弱勢清洗 (Weakness Purge)：跌破 50MA 或 RS<55 直接斬首 (對標 QS 被踢出)
        if data['P'] < data['Stop_Loss'] or rs < 55: 
            continue
            
        roe = info.get('returnOnEquity') or 0
        div_yield = info.get('dividendYield') or 0
        sec = info.get('sector', 'Unknown')
        
        # 評分權重：動能 + 現金流護城河 (高股息)
        score = (rs * 0.6) + (roe * 100 * 0.2) + (div_yield * 100 * 0.2)
        
        # 🎯 V130 狙擊手指令 (對標截圖)
        dist = data['Dist20']
        if dist > 5.0:
            action, msg = f"👀觀({round(dist,1)}%)", "高位乖離，抱緊觀望"
        elif -3.5 <= dist <= -0.5 and data['Is_VDU']:
            action, msg = f"🎯加({round(dist,1)}%)", "對標 TRGP/PWR: 完美縮量回踩，狙擊加倉"
            score *= 1.3 # 給予狙擊買點極高權重，擠進 Top 10
        elif dist < -4.0:
            action, msg = f"⚠️汰({round(dist,1)}%)", "破位警告，準備清洗"
            score *= 0.7
        else:
            action, msg = f"📈抱({round(dist,1)}%)", "趨勢合理，安心持有"
            
        all_cands.append({
            "Ticker": t, "Sector": sec[:10], "Score": score, "Action": action, "Msg": msg, 
            "RS": rs, "ROE": f"{round(roe*100, 1)}%", "DIV": f"{round(div_yield*100, 1)}%", 
            "Dist20": f"{round(dist, 1)}%", "Price": data['P'], "Hard_Stop": data['Stop_Loss']
        })

    # 📌 精選 Top 10 (能源板塊優先納入)
    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_10, s_cnt = [], {}
    for r in all_cands:
        if s_cnt.get(r['Sector'], 0) >= 3: continue 
        top_10.append(r)
        s_cnt[r['Sector']] = s_cnt.get(r['Sector'], 0) + 1
        if len(top_10) >= TARGET_POSITIONS: break

    # 計算資金分配
    allocation_per_stock = PORTFOLIO_CAPITAL / max(len(top_10), 1)
    
    matrix = []
    headers = ["排名", "代碼", "板塊", "V130作戰指令", "行動理由", "RS_Rank", "ROE", "股息率(能源)", "價格", "🛑 50MA 止損線", "建議買入股數", "倉位佔比", "更新時間"]
    
    m_status = f"VIX平穩 | 🚀 積極進攻 | 策略: 能源輪動 & 弱勢清洗 (QS遭斬首)"
    matrix.append([f"Master Sniper V130 (A股實盤映射版)", f"更新: {update_time} | 狀態: {m_status}", ""] + [""] * 10)
    matrix.append(headers)
    
    for i, r in enumerate(top_10):
        shares = math.floor(allocation_per_stock / (r['Price'] * 100)) * 100
        actual_cost = shares * r['Price']
        weight_pct = (actual_cost / PORTFOLIO_CAPITAL) * 100
        
        matrix.append([
            f"T{i+1}", f"👑 {r['Ticker']}", r['Sector'], r['Action'], r['Msg'], 
            f"{round(r['RS'], 1)}", r['ROE'], r['DIV'], 
            f"¥{round(r['Price'], 2)}", f"¥{round(r['Hard_Stop'], 2)}", 
            f"{shares:,} 股", f"{round(weight_pct, 2)}%", update_time
        ])

    print(f"📤 正在推送 V130 狙擊手陣型至 Google Sheets...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200:
        print("✅ V130 數據已成功推送！準備執行能源輪動與精準狙擊。")
    else:
        print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_super_growth_a()
