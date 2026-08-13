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
# 1. 系統配置中心 (V180 先勝後戰版)
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"
TARGET_SHEET = "A_Super" 
PORTFOLIO_CAPITAL = 1000000  
TARGET_POSITIONS = 10  

# 🚀 V180 動量股票池 (涵蓋AI算力、半導體、高息與消費)
GURU_LIST_A =[
    # AI算力/半導體/硬體 (主戰場)
    "688256.SS", "000938.SZ", "000977.SZ", "688041.SS", "603019.SS", "300454.SZ", "603986.SS",
    # 週期擴散/實體經濟 (對標之前的大神換股)
    "600938.SS", "601816.SS", "002352.SZ", "600754.SS", "600030.SS", "300059.SZ",
    # 防禦與醫藥 (護城河)
    "603259.SS", "600276.SS", "601888.SS", "600893.SS", "300759.SZ"
]

def get_universe_a(): return list(set(GURU_LIST_A))

def get_ret(series, days):
    if series is None or len(series) < days + 1: return 0.0
    val = float(series.iloc[-(days+1)])
    return (float(series.iloc[-1]) / val) - 1 if val != 0 else 0.0

def fetch_info_a(t):
    ticker = yf.Ticker(t)
    for i in range(2):
        try:
            time.sleep(random.uniform(0.1, 0.2))
            info = ticker.info
            if info and 'industry' in info:
                return t, str(info.get('sector', 'Unknown'))
        except: time.sleep(0.3)
    return t, 'Unknown'

# ==========================================
# 3. 核心量化模型 V180 (紅黑線引擎)
# ==========================================
def run_super_growth_a():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = get_universe_a()
    print("\n" + "="*65)
    print(f"🎯 [A股 先勝後戰 V180] 啟動 | 載入「紅線(戰術)與黑線(戰略)」幾何突破演算法...")

    hist_all = yf.download(universe, period="2y", progress=False, threads=False)
    if hist_all.empty: return
    
    close_df = hist_all['Close']
    high_df = hist_all['High']
    vol_df = hist_all['Volume']
    
    tech_pool = {}
    for t in universe:
        try:
            c = close_df[t].dropna()
            h = high_df[t].dropna()
            v = vol_df[t].dropna()
            p = float(c.iloc[-1])
            if len(c) < 150 or p < 1.0: continue
            
            # 📊 V180 幾何引擎：計算紅線與黑線
            # 為了避免被這兩天的突破高點干擾，我們把高點計算往前推移(shift) 3 天
            # 黑線 (宏觀防線)：過去 60 天的最高點 (Swing High)
            black_line = float(h.shift(3).rolling(window=60).max().iloc[-1])
            # 紅線 (局部頸線)：過去 20 天的最高點
            red_line = float(h.shift(3).rolling(window=20).max().iloc[-1])
            
            # 計算距離紅黑線的乖離
            dist_black = ((p - black_line) / black_line) * 100
            dist_red = ((p - red_line) / red_line) * 100
            
            # 動量與量價分析
            ret_1m = get_ret(c, 21)
            ret_6m = get_ret(c, 126)
            rs_raw = (ret_1m * 0.4) + (ret_6m * 0.6)
            
            vol_50d_avg = float(v.tail(50).mean())
            is_vdu = float(v.tail(3).mean()) < (vol_50d_avg * 0.8) # 量縮確認
            
            tech_pool[t] = {
                "P": p, "BlackLine": black_line, "RedLine": red_line, 
                "DistBlack": dist_black, "DistRed": dist_red,
                "RS_Raw": rs_raw, "Is_VDU": is_vdu, "Ret6M": ret_6m
            }
        except: continue

    # 計算相對強度排名
    df_metrics = pd.DataFrame.from_dict(tech_pool, orient='index')
    rs_ranks = (df_metrics['RS_Raw'].rank(pct=True) * 100).to_dict()

    sectors = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        for t, sec in executor.map(fetch_info_a, list(tech_pool.keys())):
            sectors[t] = sec

    all_cands = []
    
    for t, data in tech_pool.items():
        rs = rs_ranks.get(t, 0)
        sec = sectors.get(t, 'Unknown')
        p = data['P']
        black = data['BlackLine']
        red = data['RedLine']
        dist_b = data['DistBlack']
        dist_r = data['DistRed']
        
        # 基礎評分 = 動量強度
        score = rs
        
        # 🎯 V180 大師決策樹：「先勝後戰」心法
        if p >= black * 0.98 and p <= black * 1.05 and data['Is_VDU'] and rs > 60:
            # 條件：已站上或極度貼近黑線，且量縮，且具備中長線動能
            action = "🎯 先勝狙擊"
            msg = "突破黑線後縮量回踩，戰略勝利確認，買入！"
            score *= 1.5 # 最高權重獎勵！
            
        elif p > black * 1.05:
            action = "🚀 戰略勝利"
            msg = "已進入籌碼真空區，長驅直入，讓利潤奔跑"
            score *= 1.2
            
        elif p > red and p < black * 0.98:
            action = "⚔️ 戰術勝利"
            msg = "突破紅線(局部頸線)，正在挑戰黑線前高防線"
            score *= 1.1
            
        elif p >= red * 0.98 and p <= red * 1.02:
            action = "👀 紅線纏鬥"
            msg = "正在測試紅線壓力，等待放量突破信號"
            
        else:
            action = "🔪 弱勢結構"
            msg = "紅黑線之下，屬於空頭陣地，觀望/汰除"
            score *= 0.1 # 壓在均線下的股票直接淘汰

        all_cands.append({
            "Ticker": t, "Sector": sec[:15], "Score": score, 
            "Action": action, "Msg": msg, "RS": rs, 
            "Price": p, "RedLine": red, "BlackLine": black, 
            "DistBlack": dist_b
        })

    # 精選 Top 10
    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_10 = all_cands[:TARGET_POSITIONS]

    # 等權重計算
    allocation_per_stock = PORTFOLIO_CAPITAL / max(len(top_10), 1)
    
    matrix = []
    headers = ["排名", "代碼", "V180 作戰信號", "大師紅黑線點評", "RS強度", "現價", "🔴 紅線 (局部頸線)", "⚫ 黑線 (宏觀防線)", "距黑線乖離", "應持股數", "更新時間"]
    
    m_status = f"心法: 先勝後戰 (站上黑線，回踩狙擊)"
    matrix.append([f"Master Sniper V180 (紅黑線戰法版)", f"狀態: {m_status}", ""] + [""] * 8)
    matrix.append(headers)
    
    for i, r in enumerate(top_10):
        shares = math.floor(allocation_per_stock / (r['Price'] * 100)) * 100
        
        matrix.append([
            f"T{i+1}", f"👑 {r['Ticker']}", r['Action'], r['Msg'], 
            f"{round(r['RS'], 1)}", f"¥{round(r['Price'], 2)}", 
            f"¥{round(r['RedLine'], 2)}", f"¥{round(r['BlackLine'], 2)}", 
            f"{round(r['DistBlack'], 2)}%", f"{shares:,} 股", update_time
        ])

    print(f"📤 正在推送 V180 紅黑線陣型至 Google Sheets...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200:
        print("✅ V180 數據已成功推送！準備好執行大神的『先勝後戰』狙擊策略。")
    else:
        print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_super_growth_a()
