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
# 1. 系統配置中心 (已鎖定最新 Web App 網址)
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycbx-ouaRxrkOKWz7tjWGG8Y3dCqJqUwXunk_7XqVhXh_Qp_6f6WC9MaYq7zlco0WeOaf/exec"
TARGET_SHEET = "A_Super" 
PORTFOLIO_CAPITAL = 1000000  
TARGET_POSITIONS = 10  

# 🚀 V190 股票池
GURU_LIST_A = [
    # 存儲/半導體/AI晶片 (對標 MU 美光)
    "603986.SS", "301308.SZ", "688525.SS", "688041.SS", "688256.SS", "002049.SZ",
    # AI伺服器與硬體 (對標 SOXX)
    "000938.SZ", "000977.SZ", "603019.SS", "300454.SZ",
    # 週期擴散/實體經濟
    "600938.SS", "601816.SS", "002352.SZ", "600754.SS",
    # 防禦與醫藥
    "603259.SS", "600276.SS", "601888.SS", "300759.SZ"
]

def get_universe_a(): 
    return list(set(GURU_LIST_A))

def fetch_info_a(t):
    ticker = yf.Ticker(t)
    for i in range(2):
        try:
            time.sleep(random.uniform(0.1, 0.2))
            info = ticker.info
            if info and 'industry' in info:
                return t, str(info.get('sector', 'Unknown'))
        except: 
            time.sleep(0.3)
    return t, 'Unknown'

# ==========================================
# 2. 核心量化模型 V190
# ==========================================
def run_super_growth_a():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = get_universe_a()
    print("\n" + "="*65)
    print(f"🎯 [A股 V190 終極版] 啟動 | 當前目標URL: {WEBAPP_URL[:45]}...")

    hist_all = yf.download(universe, period="1y", progress=False, threads=False)
    if hist_all.empty: 
        print("❌ 無法獲取股票歷史數據，請稍後再試。")
        return
    
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
            if len(c) < 100 or p < 1.0: continue
            
            typical_price = c
            vwap_20_red = (typical_price * v).rolling(window=20).sum() / v.rolling(window=20).sum()
            vwap_60_blue = (typical_price * v).rolling(window=60).sum() / v.rolling(window=60).sum()
            
            v_red = float(vwap_20_red.iloc[-1])
            v_blue = float(vwap_60_blue.iloc[-1])
            
            black_line = float(h.shift(3).rolling(window=60).max().iloc[-1])
            red_line = float(h.shift(3).rolling(window=20).max().iloc[-1])
            
            was_below = float(c.iloc[-4]) < float(vwap_20_red.iloc[-4]) or float(c.iloc[-4]) < float(vwap_60_blue.iloc[-4])
            is_above_now = p > v_red and p > v_blue
            
            tech_pool[t] = {
                "P": p, "VWAP_Red": v_red, "VWAP_Blue": v_blue, 
                "BlackLine": black_line, "RedLine": red_line,
                "WasBelow": was_below, "IsAboveNow": is_above_now,
                "RS_Raw": (float(c.iloc[-1])/float(c.iloc[-21]) - 1)*0.4 + (float(c.iloc[-1])/float(c.iloc[-63]) - 1)*0.6
            }
        except: continue

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
        v_red, v_blue = data['VWAP_Red'], data['VWAP_Blue']
        black = data['BlackLine']
        score = rs
        
        if data['IsAboveNow'] and data['WasBelow'] and rs > 60:
            action = "🔥 MU式雙線突破"
            msg = "剛剛放量站上 VWAP 與全換手均線，套牢盤清空，主升段點火！"
            score *= 1.5
        elif p >= black * 0.98 and p <= black * 1.05 and rs > 70:
            action = "🎯 先勝回踩狙擊"
            msg = "突破黑線前高後回踩確認，戰略勝利，精準狙擊！"
            score *= 1.3
        elif p > v_red > v_blue:
            action = "🚀 籌碼多頭排列"
            msg = "現價 > VWAP > 全換手線，籌碼真空，讓利潤奔跑"
            score *= 1.1
        elif p < v_red and p < v_blue:
            action = "🔪 均線死穴"
            msg = "被 VWAP 與換手線死死壓制，空頭排列，無情汰除"
            score *= 0.1
        else:
            action = "👀 籌碼纏鬥"
            msg = "在兩條均線間震盪，等待方向突破"
            score *= 0.5

        all_cands.append({
            "Ticker": t, "Sector": sec[:15], "Score": score, 
            "Action": action, "Msg": msg, "RS": rs, "Price": p, 
            "VWAP_Red": v_red, "VWAP_Blue": v_blue, "BlackLine": black
        })

    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_10 = all_cands[:TARGET_POSITIONS]

    allocation_per_stock = PORTFOLIO_CAPITAL / max(len(top_10), 1)
    
    matrix = []
    headers = ["排名", "代碼", "V190 大師圖表信號", "量價籌碼解析", "RS強度", "現價", "🔴 VWAP加權均線", "🔵 全換手均線", "⚫ 宏觀黑線(前高)", "應持股數", "更新時間"]
    
    m_status = f"核心: MU雙線突破 (紅藍線) + SOXX先勝後戰 (黑線)"
    matrix.append([f"Master Sniper V190 (全籌碼突破版)", f"狀態: {m_status}", ""] + [""] * 8)
    matrix.append(headers)
    
    for i, r in enumerate(top_10):
        shares = math.floor(allocation_per_stock / (r['Price'] * 100)) * 100
        matrix.append([
            f"T{i+1}", f"👑 {r['Ticker']}", r['Action'], r['Msg'], 
            f"{round(r['RS'], 1)}", f"¥{round(r['Price'], 2)}", 
            f"¥{round(r['VWAP_Red'], 2)}", f"¥{round(r['VWAP_Blue'], 2)}", 
            f"¥{round(r['BlackLine'], 2)}", f"{shares:,} 股", update_time
        ])

    print(f"📤 準備推送 {len(matrix)} 行數據至 [{TARGET_SHEET}] 分頁...")
    res = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    print("後台 HTTP 狀態碼:", res.status_code)
    print("後台完整回應:", res.text)
    
    if res.status_code == 200:
        print("\n✅ 推送成功！請刷新 Google Sheets 檢視。")

if __name__ == "__main__":
    run_super_growth_a()
