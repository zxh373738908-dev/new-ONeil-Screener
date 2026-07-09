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
# 1. 系統配置中心 (V150 新主線輪動與強制再平衡版)
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"
TARGET_SHEET = "A_Super" 
PORTFOLIO_CAPITAL = 1000000  
TARGET_POSITIONS = 10  # 嚴格限制 10 檔持倉

# 🚀 V150 股票池大換血：對標 RDDT 與 GEV
GURU_LIST_A =[
    # 🆕 新主線 1：AI數據/語料庫/互聯網平台 (對標 RDDT)
    "603000.SS", # 人民網 (AI數據要素)
    "300364.SZ", # 中文在線 (AI語料/IP)
    "300418.SZ", # 昆侖萬維 (AI軟體/平台)
    
    # 🆕 新主線 2：新型電力設備/電網基建 (對標 GEV)
    "601179.SS", # 中國西電 (特高壓/電力設備)
    "600312.SS", # 平高電氣 (電網設備)
    "600406.SS", # 國電南瑞 (智能電網)
    
    # 留存的強勢防禦與醫療 (對標 LLY)
    "603259.SS", "600276.SS",
    # 留存的低軌衛星/軍工 (之前 IRDM/ATI 對標)
    "601698.SS", "600893.SS", "688122.SS",
    # 留存的困境反轉/平台 (ROKU 對標)
    "300413.SZ", "002027.SZ"
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
                    'returnOnEquity': info.get('returnOnEquity', 0)
                }
        except: time.sleep(0.3)
    return t, {}

def get_ret(series, days):
    if series is None or len(series) < days + 1: return 0.0
    val = float(series.iloc[-(days+1)])
    return (float(series.iloc[-1]) / val) - 1 if val != 0 else 0.0

# ==========================================
# 3. 核心量化模型 V150
# ==========================================
def run_super_growth_a():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = get_universe_a()
    print("\n" + "="*65)
    print(f"⚖️ [A股 Master Sniper V150] 啟動 | 載入「組合再平衡」與「RDDT/GEV新主線」引擎...")

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
            ema10 = float(c.ewm(span=10, adjust=False).mean().iloc[-1])
            ema20 = float(c.ewm(span=20, adjust=False).mean().iloc[-1])
            dist_20ema = ((p - ema20) / ema20) * 100
            
            ret_21 = get_ret(c, 21)
            ret_63 = get_ret(c, 63)
            rs_raw = (ret_21 * 0.4) + (ret_63 * 0.4) + (get_ret(c, 126) * 0.2)
            
            vol_50d_avg = float(v.tail(50).mean())
            is_vdu = float(v.tail(3).mean()) < (vol_50d_avg * 0.8)
            
            tech_pool[t] = {
                "P": p, "Dist20": dist_20ema, "EMA10": ema10, "Stop_Loss": m50,
                "RS_Raw": rs_raw, "Ret21": ret_21, "Ret63": ret_63, "Is_VDU": is_vdu
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
        roe = info.get('returnOnEquity') or 0
        sec = info.get('sector', 'Unknown')
        
        score = (rs * 0.7) + (roe * 100 * 0.3)
        p, ema10, dist = data['P'], data['EMA10'], data['Dist20']
        
        # 🎯 V150 核心決策樹 (對標大神新動作)
        is_pwr_mu_take_profit = data['Ret63'] > 0.2 and p < ema10 and dist < 2.0
        
        if p < data['Stop_Loss']:
            continue # 跌破 50MA 無情清洗
            
        elif is_pwr_mu_take_profit:
            action, msg = "💰 獲利了結", "對標 PWR/MU: 動能衰退，賣出贏家騰出資金"
            score *= 0.5 # 降級，準備被替換
            
        elif 0 <= dist <= 5.0 and data['Ret21'] > 0.1:
            action, msg = "🔥 新主線建倉", "對標 RDDT/GEV: 剛起漲之新週期，積極佈局"
            score *= 1.4 # 大幅獎勵新主線
            
        elif dist > 8.0:
            action, msg = "🚀 讓利潤奔跑", "高位強勢，等待再平衡信號"
            
        elif -3.0 <= dist <= 0 and data['Is_VDU']:
            action, msg = "🎯 狙擊加倉", "對標 ROKU: 縮量回踩，絕佳買回點"
            
        else:
            action, msg = "📈 等權重抱緊", "趨勢合理，維持 10% 權重"
            
        all_cands.append({
            "Ticker": t, "Sector": sec[:10], "Score": score, "Action": action, "Msg": msg, 
            "RS": rs, "ROE": f"{round(roe*100, 1)}%", "Dist20": f"{round(dist, 1)}%", 
            "Price": p, "Hard_Stop": data['Stop_Loss']
        })

    # 📌 精選 Top 10 
    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_10, s_cnt = [], {}
    for r in all_cands:
        if s_cnt.get(r['Sector'], 0) >= 3: continue 
        top_10.append(r)
        s_cnt[r['Sector']] = s_cnt.get(r['Sector'], 0) + 1
        if len(top_10) >= TARGET_POSITIONS: break

    # ⚖️ 執行「強制再平衡 (Forced Equal-Weight Rebalance)」
    # 不管之前的股票漲多少，現在全部強制均分資金，每檔 10 萬
    allocation_per_stock = PORTFOLIO_CAPITAL / max(len(top_10), 1)
    
    matrix = []
    headers = ["排名", "代碼", "板塊", "V150 大師指令", "交割單對標邏輯", "RS動能", "ROE護城河", "20EMA乖離", "當前價格", "🛑 50MA 止損", "⚖️ 再平衡應持股數", "目標倉位佔比", "更新時間"]
    
    m_status = f"策略: 組合強制再平衡 (10%等權重) + 高低切換"
    matrix.append([f"Master Sniper V150 (再平衡與新主線版)", f"更新: {update_time} | 狀態: {m_status}", ""] + [""] * 10)
    matrix.append(headers)
    
    for i, r in enumerate(top_10):
        # 嚴格的 100 股向下取整
        shares = math.floor(allocation_per_stock / (r['Price'] * 100)) * 100
        actual_cost = shares * r['Price']
        weight_pct = (actual_cost / PORTFOLIO_CAPITAL) * 100
        
        matrix.append([
            f"T{i+1}", f"👑 {r['Ticker']}", r['Sector'], r['Action'], r['Msg'], 
            f"{round(r['RS'], 1)}", r['ROE'], r['Dist20'], 
            f"¥{round(r['Price'], 2)}", f"¥{round(r['Hard_Stop'], 2)}", 
            f"{shares:,} 股", f"{round(weight_pct, 2)}%", update_time
        ])

    print(f"📤 正在推送 V150 強制再平衡陣型至 Google Sheets...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200:
        print("✅ V150 數據已成功推送！系統已完成等權重再平衡。")
    else:
        print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_super_growth_a()
