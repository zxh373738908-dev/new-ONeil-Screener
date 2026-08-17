import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import requests
import warnings
import time

warnings.filterwarnings('ignore')

# ==========================================
# 1. 系統配置中心 (V3.0 TheMarketMemo 動量法則)
# ==========================================
# 寫入您的最新 Webhook URL
WEBAPP_URL = "https://script.google.com/macros/s/AKfycbw_f6Uy1OMIIl-4mLsAaxe1rXr64qYf2j0RHoKl3-xu0QOp-5kqFpk9rTBIV9Yf5-kz/exec"
TARGET_SHEET = "O'Neil Watchlist"  # 🎯 寫入您截圖中的歐奈爾觀察列表
BENCHMARK = "QQQ" # 基準指數，用於計算相對動量線 (RS Line)

# 🚀 動量股票池 (包含文章提到的 FTI, NVDA 以及熱門 SaaS/半導體/能源等)
GURU_LIST = [
    "NVDA", "FTI", "OIH", "SHOP", "TEAM", "CRWD", "DDOG", "SNOW", "PLTR", 
    "NOW", "WDAY", "ZS", "NET", "MDB", "AMD", "MU", "AVGO", "TSM", "ARM", 
    "SMCI", "META", "AMZN", "MSFT", "GOOGL", "TSLA", "CEG", "VST"
]

def get_universe(): return list(set(GURU_LIST))

# ==========================================
# 2. 技術指標計算函數
# ==========================================
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# ==========================================
# 3. 核心量化模型 V3.0
# ==========================================
def run_market_memo_momentum():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = get_universe()
    universe.append(BENCHMARK) # 加入基準指數下載數據
    
    print("\n" + "="*70)
    print(f"🎯 [V3.0 歐奈爾/MarketMemo 動量引擎] 啟動...")
    print(f"載入: RPS 加權排名、動量線 (vs {BENCHMARK})、RSI 回調點位、兩點鐘仰角...")

    # 下載近半年多一點的數據 (約130個交易日滿足120R計算)
    hist_all = yf.download(universe, period="1y", progress=False, threads=True)
    if hist_all.empty: return
    
    close_df = hist_all['Close']
    
    # 提取基準指數 (QQQ) 收盤價
    bm_close = close_df[BENCHMARK].dropna()
    
    # --- 第一階段：計算所有股票的漲跌幅以進行 RPS 排名 ---
    returns_pool = {}
    for t in get_universe():
        c = close_df[t].dropna()
        if len(c) < 125: continue # 確保有足夠天數
        
        # 計算 20日, 60日, 120日 漲幅
        ret_20 = c.iloc[-1] / c.iloc[-21] - 1
        ret_60 = c.iloc[-1] / c.iloc[-61] - 1
        ret_120 = c.iloc[-1] / c.iloc[-121] - 1
        
        returns_pool[t] = {"Ret20": ret_20, "Ret60": ret_60, "Ret120": ret_120}

    # 轉換為 DataFrame 並計算百分位排名 (0~100分)
    df_returns = pd.DataFrame.from_dict(returns_pool, orient='index')
    df_returns['20R'] = df_returns['Ret20'].rank(pct=True) * 100
    df_returns['60R'] = df_returns['Ret60'].rank(pct=True) * 100
    df_returns['120R'] = df_returns['Ret120'].rank(pct=True) * 100
    
    # 🎯 TheMarketMemo 核心公式：加權總排名分數
    df_returns['Total_Rank'] = 0.2 * df_returns['20R'] + 0.4 * df_returns['60R'] + 0.4 * df_returns['120R']

    # --- 第二階段：計算個股技術型態 (動量線、兩點鐘仰角、RSI) ---
    tech_pool = []
    
    for t in df_returns.index:
        c = close_df[t].dropna()
        p = float(c.iloc[-1])
        
        # 1. 計算 VWAP (此處簡化以收盤價的均線代替，實戰可加上成交量)
        ma_20 = c.rolling(20).mean()
        ma_slope_pct = (ma_20.iloc[-1] - ma_20.iloc[-6]) / ma_20.iloc[-6]
        is_2_oclock = ma_slope_pct > 0.015 # 兩點鐘方向
        
        # 2. 計算 RSI (尋找回調買點)
        rsi = calculate_rsi(c, 14).iloc[-1]
        
        # 3. 計算動量線 (Relative Strength Line) = 個股 / QQQ
        rs_line = c / bm_close
        rs_line_ma = rs_line.rolling(50).mean() # 動量線的 50日均線
        
        rs_line_current = rs_line.iloc[-1]
        rs_line_ma_current = rs_line_ma.iloc[-1]
        rs_line_ma_5d_ago = rs_line_ma.iloc[-6]
        
        # 判斷：動量線 > 均線，且 均線向上運行
        rs_line_bullish = (rs_line_current > rs_line_ma_current) and (rs_line_ma_current > rs_line_ma_5d_ago)
        
        total_rank = df_returns.loc[t, 'Total_Rank']
        
        # 🎯 V3.0 決策樹 (嚴格遵循 MarketMemo 邏輯)
        score = total_rank
        
        if total_rank >= 80 and rs_line_bullish and rsi < 60 and is_2_oclock:
            action = "🔥 完美回調買點"
            msg = f"Rank>80且動量線強勢。RSI({round(rsi,1)})回調，加上兩點鐘仰角，絕佳切入點！"
            score += 100 
            
        elif total_rank >= 80 and rs_line_bullish:
            action = "🚀 領導股續抱"
            msg = "動量排名霸榜，且相對 QQQ 走勢強勁。順勢而為，留意 -8% 止損。"
            score += 50
            
        elif total_rank >= 70 and is_2_oclock:
            action = "📈 潛力蓄勢"
            msg = "動量剛起步(兩點鐘方向)，等待 Rank 突破 80 確認領導地位。"
            score += 20
            
        elif total_rank < 50:
            action = "🗑️ 弱勢標的"
            msg = "排名落後，動量衰竭，依據紀律汰弱留強。"
            score -= 50
            
        else:
            action = "👀 整理觀察"
            msg = "動量不夠極端，動量線或斜率未達標，持續觀察。"

        tech_pool.append({
            "Ticker": t, "Total_Rank": total_rank, "R20": df_returns.loc[t, '20R'], 
            "R60": df_returns.loc[t, '60R'], "R120": df_returns.loc[t, '120R'],
            "RSI": rsi, "Slope": ma_slope_pct, "Action": action, "Msg": msg, 
            "Price": p, "Score": score
        })

    # 精選排序
    tech_pool.sort(key=lambda x: x['Score'], reverse=True)
    top_results = tech_pool[:15]
    
    # --- 第三階段：推送到 Google Sheets ---
    matrix = []
    headers = ["排名", "代碼", "V3 決策信號", "TheMarketMemo 邏輯解析", "🏆 Total Rank", "20R (0.2)", "60R (0.4)", "120R (0.4)", "RSI (進場)", "均線仰角", "現價", "更新時間"]
    
    m_status = f"策略: RPS>80領導股 + 動量線強於QQQ + RSI回調進場 + 兩點鐘仰角"
    matrix.append([f"O'Neil / MarketMemo V3.0", f"狀態: {m_status}", ""] + [""] * 9)
    matrix.append(headers)
    
    for i, r in enumerate(top_results):
        slope_str = f"{r['Slope']*100:+.2f}%" 
        
        matrix.append([
            f"T{i+1}", f"👑 {r['Ticker']}", r['Action'], r['Msg'], 
            f"{round(r['Total_Rank'], 1)} 分", f"{round(r['R20'], 1)}", 
            f"{round(r['R60'], 1)}", f"{round(r['R120'], 1)}", 
            f"{round(r['RSI'], 1)}", slope_str, f"${round(r['Price'], 2)}", update_time
        ])

    print(f"📤 正在推送 V3.0 動量陣型至 Google Sheets ({TARGET_SHEET})...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200:
        print("✅ 數據已成功寫入！您的「機構級動量篩選器」已準備就緒。")
    else:
        print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_market_memo_momentum()
