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
# 1. 系統配置中心 (V170 多週期動量熱力圖版)
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"
TARGET_SHEET = "A_Super" 
PORTFOLIO_CAPITAL = 1000000  
TARGET_POSITIONS = 9  # 根據截圖，大神的持倉收斂到 9 檔

# 🚀 V170 股票池大換血：AI 科技硬體王者歸來
GURU_LIST_A =[
    # 🆕 新增：AI伺服器/硬體基礎設施 (對標 HPE, ARW)
    "000977.SZ", # 浪潮信息 (AI伺服器龍頭)
    "603019.SS", # 中科曙光 (算力基礎設施)
    "000938.SZ", # 紫光股份 (ICT設備)
    
    # 🆕 新增：半導體/算力晶片 (對標 AMD)
    "688041.SS", # 海光信息 (國產CPU/DCU)
    "688256.SS", # 寒武紀 (AI晶片)
    
    # 🆕 新增：網路安全 (對標 FTNT)
    "300454.SZ", # 深信服
    "002439.SZ", # 啟明星辰
    
    # 🛡️ 保留倖存者：高端消費、金融、特種材料、衛星、酒店 (VIK, STT, ATI, VSAT, HST)
    "601888.SS", # 中國中免 (高端消費)
    "300059.SZ", # 東方財富 (金融)
    "600893.SS", # 航發動力 (特種材料/軍工)
    "601698.SS", # 中國衛通 (衛星通訊)
    "600754.SS"  # 錦江酒店 (酒店房產)
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
# 3. 核心量化模型 V170 (多週期引擎)
# ==========================================
def run_super_growth_a():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = get_universe_a()
    print("\n" + "="*65)
    print(f"🔥 [A股 Momentum Portfolio V170] 啟動 | 載入多週期熱力圖與洗盤狙擊演算法...")

    # 拉取 2 年數據以確保能計算 1 年期 (252天) 報酬
    hist_all = yf.download(universe, period="2y", progress=False, threads=False)
    if hist_all.empty: return
    close_df = hist_all['Close']
    
    tech_pool = {}
    for t in universe:
        try:
            c = close_df[t].dropna()
            p = float(c.iloc[-1])
            if len(c) < 252 or p < 1.0: continue # 確保有1年歷史
            
            ret_1d = get_ret(c, 1)
            ret_1m = get_ret(c, 21)   # 1M = 21 交易日
            ret_6m = get_ret(c, 126)  # 6M = 126 交易日
            ret_1y = get_ret(c, 252)  # 1Y = 252 交易日
            
            spark = ",".join([str(round(val, 2)) for val in c.tail(60).tolist()])
            
            tech_pool[t] = {
                "P": p, "Ret1D": ret_1d, "Ret1M": ret_1m, "Ret6M": ret_6m, "Ret1Y": ret_1y, "Spark": spark
            }
        except: continue

    # 📊 V170 核心：計算全市場的百分位排名 (Percentile Rank)
    df_metrics = pd.DataFrame.from_dict(tech_pool, orient='index')
    rank_1m = (df_metrics['Ret1M'].rank(pct=True) * 100).to_dict()
    rank_6m = (df_metrics['Ret6M'].rank(pct=True) * 100).to_dict()
    rank_1y = (df_metrics['Ret1Y'].rank(pct=True) * 100).to_dict()

    sectors = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        for t, sec in executor.map(fetch_info_a, list(tech_pool.keys())):
            sectors[t] = sec

    all_cands = []
    
    for t, data in tech_pool.items():
        r_1m = rank_1m.get(t, 0)
        r_6m = rank_6m.get(t, 0)
        r_1y = rank_1y.get(t, 0)
        sec = sectors.get(t, 'Unknown')
        
        # 綜合評分：更看重中長線動能 (6M 和 1Y)
        score = (r_1m * 0.2) + (r_6m * 0.5) + (r_1y * 0.3)
        
        # 🎯 V170 大師決策樹 (完美對標 AMD/HPE 邏輯)
        if r_6m > 85 and r_1y > 80 and r_1m < 40:
            action = "🎯 長線洗盤狙擊"
            score *= 1.5 # 大幅加分，強迫選入 AMD 類型的標的
        elif r_1m > 70 and r_6m > 80:
            action = "🔥 動能全面爆發"
        elif r_6m > 60 and r_1y > 60:
            action = "📈 長線趨勢抱緊"
        else:
            action = "🔪 動能流失汰除"
            score *= 0.1 # 長線動能轉弱直接淘汰
            
        all_cands.append({
            "Ticker": t, "Sector": sec[:15], "Price": data['P'], 
            "Ret1D": data['Ret1D'], "Ret1M": data['Ret1M'],
            "Trend": f'=SPARKLINE({{{data["Spark"]}}}, {{"charttype","line";"linewidth",1;"color","black"}})',
            "R_1M": r_1m, "R_6M": r_6m, "R_1Y": r_1y,
            "Score": score, "Action": action
        })

    # 精選 Top 9 (對標截圖)
    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_9 = all_cands[:TARGET_POSITIONS]

    # 等權重計算
    allocation_per_stock = PORTFOLIO_CAPITAL / max(len(top_9), 1)
    
    matrix = []
    # 完美復刻原圖表頭
    headers = ["Ticker", "Sector", "Last Price", "1D%", "1M%", "1Y Trend (60D)", "1M Rank", "6M Rank", "1Y Rank", "V170 大師決策", "應持股數"]
    
    m_status = f"2026-08 | 策略: 科技股王者歸來 & 長線贏家洗盤狙擊"
    matrix.append([f"9 動量組合 (Momentum Portfolio)", f"狀態: {m_status}", ""] + [""] * 8)
    matrix.append(headers)
    
    for r in top_9:
        shares = math.floor(allocation_per_stock / (r['Price'] * 100)) * 100
        
        matrix.append([
            f"👑 {r['Ticker']}", r['Sector'], f"{round(r['Price'], 2)}", 
            f"{round(r['Ret1D']*100, 2)}%", f"{round(r['Ret1M']*100, 2)}%", 
            r['Trend'], 
            # 這些分數將在 G-Sheets 中成為熱力圖的來源
            round(r['R_1M']), round(r['R_6M']), round(r['R_1Y']), 
            r['Action'], f"{shares:,}"
        ])

    print(f"📤 正在推送 V170 多週期熱力圖至 Google Sheets...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200:
        print("✅ V170 數據已成功推送！請在 Google Sheets 設定條件式格式設定以呈現熱力圖效果。")
    else:
        print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_super_growth_a()
