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
# 1. 系統配置中心 (A股 V2.0 動量組合版)
# ==========================================
# 🔄 已更新為您提供的最新 Webhook URL
WEBAPP_URL = "https://script.google.com/macros/s/AKfycbw_f6Uy1OMIIl-4mLsAaxe1rXr64qYf2j0RHoKl3-xu0QOp-5kqFpk9rTBIV9Yf5-kz/exec"
TARGET_SHEET = "A-Share screener"  # 🎯 指定寫入的 Google Sheet 表格名稱
PORTFOLIO_CAPITAL = 1000000  
TARGET_POSITIONS = 10  

# 🚀 A股股票池 (半導體/AI算力/硬體等高彈性板塊)
GURU_LIST_A = [
    # 存儲/半導體/AI晶片
    "603986.SS", "301308.SZ", "688525.SS", "688041.SS", "688256.SS", "002049.SZ",
    # AI伺服器與硬體
    "000938.SZ", "000977.SZ", "603019.SS", "300454.SZ",
    # 週期擴散/實體經濟
    "600938.SS", "601816.SS", "002352.SZ", "600754.SS",
    # 防禦與醫藥
    "603259.SS", "600276.SS", "601888.SS", "300759.SZ"
]

def get_universe_a(): return list(set(GURU_LIST_A))

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
# 3. 核心量化模型 V2.0 (底部反轉 + 雙線突破 + 兩點鐘方向)
# ==========================================
def run_momentum_portfolio_a():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = get_universe_a()
    print("\n" + "="*70)
    print(f"🎯 [A股 動量組合 V2.0] 啟動 | 載入「底部反轉 + 雙線突破 + 兩點鐘方向」引擎...")

    hist_all = yf.download(universe, period="1y", progress=False, threads=False)
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
            if len(c) < 100 or p < 1.0: continue
            
            # 📊 引擎 1：計算 VWAP 加權均線 (紅: 20日) 與 全換手均線擬合 (藍: 60日)
            typical_price = c 
            vwap_20_red = (typical_price * v).rolling(window=20).sum() / v.rolling(window=20).sum()
            vwap_60_blue = (typical_price * v).rolling(window=60).sum() / v.rolling(window=60).sum()
            
            v_red = float(vwap_20_red.iloc[-1])
            v_blue = float(vwap_60_blue.iloc[-1])
            
            # 📈 引擎 2：計算「兩點鐘方向」(均線斜率/動量)
            # 對比現在與 5 天前的 VWAP，計算均線仰角。正值越大，仰角越陡。
            v_red_5d_ago = float(vwap_20_red.iloc[-6])
            vwap_slope_pct = (v_red - v_red_5d_ago) / v_red_5d_ago
            
            # 5天內 VWAP 上揚超過 1.5% 視為進入「兩點鐘方向」的強勢仰角
            is_2_oclock = vwap_slope_pct > 0.015  
            
            # 📊 引擎 3：宏觀壓力線
            black_line = float(h.shift(3).rolling(window=60).max().iloc[-1])
            
            # 判斷近三天內是否剛從 VWAP 均線下方突破上來 (底部反轉特徵)
            was_below = float(c.iloc[-4]) < float(vwap_20_red.iloc[-4]) or float(c.iloc[-4]) < float(vwap_60_blue.iloc[-4])
            is_above_now = p > v_red and p > v_blue
            
            tech_pool[t] = {
                "P": p, "VWAP_Red": v_red, "VWAP_Blue": v_blue, 
                "BlackLine": black_line, "VWAP_Slope": vwap_slope_pct,
                "WasBelow": was_below, "IsAboveNow": is_above_now, "Is2Oclock": is_2_oclock,
                # 動量 RS 評分 
                "RS_Raw": (float(c.iloc[-1])/float(c.iloc[-21]) - 1)*0.5 + (float(c.iloc[-1])/float(c.iloc[-63]) - 1)*0.5
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
        
        # 🎯 V2.0 A股動量決策樹：融入「兩點鐘方向」
        
        # 第一優先：底部反轉 + 雙線突破 + 兩點鐘方向
        if data['IsAboveNow'] and data['WasBelow'] and data['Is2Oclock']:
            action = "🔥 完美反轉突破 (兩點鐘動量)"
            msg = "剛剛放量站上雙線，且均線呈現完美『兩點鐘方向』仰角，主升段暴力啟動！"
            score *= 2.0 # 絕對最高權重！
            
        # 第二優先：純雙線突破 (還在醞釀兩點鐘仰角)
        elif data['IsAboveNow'] and data['WasBelow'] and not data['Is2Oclock']:
            action = "📈 底部剛突破"
            msg = "剛站上 VWAP 雙線，等待均線斜率拐頭向上確認動量。"
            score *= 1.3
            
        # 第三優先：已在多頭趨勢且維持兩點鐘方向
        elif p > v_red > v_blue and data['Is2Oclock']:
            action = "🚀 強勢動量續航"
            msg = "籌碼多頭排列，斜率維持『兩點鐘方向』，強勢逼空！"
            score *= 1.5
            
        # 均線壓制或斜率朝下
        elif p < v_red and data['VWAP_Slope'] < 0:
            action = "🔪 均線死穴 (下降趨勢)"
            msg = "跌破均線且斜率朝下，無情汰除"
            score *= 0.1
            
        else:
            action = "👀 籌碼纏鬥"
            msg = "無明顯方向或動量不足，持續觀察"
            score *= 0.5

        all_cands.append({
            "Ticker": t, "Sector": sec[:15], "Score": score, 
            "Action": action, "Msg": msg, "RS": rs, "Price": p, 
            "VWAP_Red": v_red, "VWAP_Blue": v_blue, 
            "Slope": data['VWAP_Slope']
        })

    # 精選 Top 10 動量標的
    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_10 = all_cands[:TARGET_POSITIONS]
    
    matrix = []
    headers = ["排名", "代碼", "V2 動量信號", "量價籌碼解析", "RS強度", "均線斜率(仰角)", "現價", "🔴 20日 VWAP", "🔵 60日 VWAP", "更新時間"]
    
    m_status = f"核心策略: 底部反轉 + 雙線突破 + 兩點鐘方向動量"
    matrix.append([f"A-Share Momentum V2.0", f"狀態: {m_status}", ""] + [""] * 7)
    matrix.append(headers)
    
    for i, r in enumerate(top_10):
        # 格式化斜率為百分比，方便判斷仰角
        slope_str = f"{r['Slope']*100:+.2f}%" 
        
        matrix.append([
            f"T{i+1}", f"👑 {r['Ticker']}", r['Action'], r['Msg'], 
            f"{round(r['RS'], 1)}", slope_str, f"¥{round(r['Price'], 2)}", 
            f"¥{round(r['VWAP_Red'], 2)}", f"¥{round(r['VWAP_Blue'], 2)}", update_time
        ])

    print(f"📤 正在推送 V2.0 A股動量陣型至 Google Sheets ({TARGET_SHEET})...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200:
        print("✅ 數據已成功寫入 A-Share screener 表格！準備在 A股獵殺『兩點鐘方向』的主升段。")
    else:
        print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_momentum_portfolio_a()
