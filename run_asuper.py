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
# 1. 系統配置中心 (V100 終極輪動策略)
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"
TARGET_SHEET = "A_Super" 
PORTFOLIO_CAPITAL = 1000000  # 模擬總資金：100萬人民幣
TARGET_POSITIONS = 10        # 嚴格等權重 10 檔持倉

# 🚀 A股全天候映射池 (新增 TWLO 雲通訊/SaaS 概念，擴大輪動池)
GURU_LIST_A =[
    # 基礎設施/液冷/電力 (PWR, VRT)
    "300408.SZ", "300308.SZ", "600487.SS", "000977.SZ", "601138.SS", "300274.SZ",
    # 雲端/SaaS/網路安全/通訊 (TWLO, OKTA, NTNX) -> 擴充此板塊以利輪動
    "688111.SS", "300033.SZ", "600588.SS", "300059.SZ", "002123.SZ", "300634.SZ", "000938.SZ",
    # 醫療壟斷/剛需 (LLY)
    "600276.SS", "300760.SZ", "603259.SS", "600436.SS",
    # 金融/交易所/印鈔機防禦 (V, NDAQ)
    "600036.SS", "601318.SS", "600519.SS", "600900.SS", "000858.SZ",
    # 困境反轉/平台 (FSLR, ROKU)
    "300750.SZ", "002594.SZ", "600690.SS", "000333.SZ", "601899.SS"
]

def get_universe_a(): return list(set(GURU_LIST_A))

# ==========================================
# 2. 基礎面與護城河獲取
# ==========================================
def fetch_info_a(t):
    ticker = yf.Ticker(t)
    for i in range(2):
        try:
            time.sleep(random.uniform(0.1, 0.2))
            info = ticker.info
            if info and 'industry' in info:
                return t, {
                    'industry': str(info.get('industry', 'Unknown')).replace('\t', ''),
                    'sector': str(info.get('sector', 'Unknown')),
                    'operatingMargins': info.get('operatingMargins', 0),
                    'revenueGrowth': info.get('revenueGrowth', 0),
                    'returnOnEquity': info.get('returnOnEquity', 0)
                }
        except: time.sleep(0.3)
    return t, {}

def get_ret(series, days):
    if series is None or len(series) < days + 1: return 0.0
    val = float(series.iloc[-(days+1)])
    return (float(series.iloc[-1]) / val) - 1 if val != 0 else 0.0

# ==========================================
# 3. 核心量化模型 V100 (不主動止盈 + TWLO均線戰法)
# ==========================================
def run_super_growth_a():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = get_universe_a()
    print("\n" + "="*60)
    print(f"🚀 [A股極致優化 V100] 啟動 | 載入「不主動止盈」與「TWLO回踩企穩」決策樹...")

    # 1. 技術面與動能掃描
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
            dist_50ma = ((p - m50) / m50) * 100
            
            rs_raw = (get_ret(c, 21)*0.4) + (get_ret(c, 63)*0.4) + (get_ret(c, 126)*0.2)
            vol_50d_avg = float(v.tail(50).mean())
            is_vdu = float(v.tail(3).mean()) < (vol_50d_avg * 0.7)
            
            tech_pool[t] = {
                "P": p, "Dist20": dist_20ema, "Dist50": dist_50ma, "RS_Raw": rs_raw,
                "VR": float(v.iloc[-1]) / vol_50d_avg if vol_50d_avg > 0 else 1.0, 
                "Is_VDU": is_vdu, "Stop_Loss": m50
            }
        except: continue

    # 2. 獲取護城河數據
    infos = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        for t, info in executor.map(fetch_info_a, list(tech_pool.keys())):
            if info: infos[t] = info

    rs_ranks = (pd.Series({t: d['RS_Raw'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()
    all_cands = []
    
    for t, data in tech_pool.items():
        info, rs = infos.get(t, {}), rs_ranks.get(t, 0)
        
        # 📌 大師汰弱留強機制：動能跌破 60 或跌破 50MA 直接淘汰 (DUOL 邏輯)
        if rs < 60 or data['Dist50'] < 0: 
            continue 

        # 護城河評分
        op_margin = info.get('operatingMargins') or 0
        rev_g = info.get('revenueGrowth') or 0
        roe = info.get('returnOnEquity') or 0
        rule_of_40 = (op_margin + rev_g) * 100
        
        fund_score = 0
        if roe > 0.15: fund_score += 15       
        if rule_of_40 > 30: fund_score += 15  
        score = (rs * 0.6) + fund_score
        
        # 📌 V100 終極決策樹 (完全對標實盤註解)
        dist = data['Dist20']
        if dist > 4.5:
            action = "🚀 不主動止盈"
            msg = f"趨勢強勁 (+{round(dist,1)}%)，讓利潤奔跑"
            score *= 1.05 # 給予強勢股微調加分，確保它們留在前10
        elif -2.0 <= dist <= 2.5 and data['Is_VDU']:
            action = "🎯 TWLO式建倉"
            msg = f"20EMA企穩且量縮，絕佳輪動點"
            score *= 1.25 # 大幅獎勵 20EMA 企穩的標的，促使系統換股
        elif dist < -3.0:
            action = "⚠️ 動量衰退"
            msg = f"跌破20EMA過深，準備DUOL式平倉"
            score *= 0.7  # 大幅扣分，將其擠出 Top 10
        else:
            action = "📈 趨勢延續"
            msg = f"乖離合理 ({round(dist,1)}%)，持股續抱"
            
        all_cands.append({
            "Ticker": t, "Sector": info.get('sector', 'Unknown')[:10], 
            "Score": score, "Action": action, "Msg": msg, "RS": rs,
            "ROE": f"{round(roe*100, 1)}%", "Rule40": f"{round(rule_of_40, 1)}", 
            "Dist20": f"{round(dist, 1)}%", "Price": data['P'], "StopLoss": data['Stop_Loss']
        })

    # 3. 嚴格板塊分散與 10檔輪動精選
    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_10, s_cnt = [], {}
    for r in all_cands:
        if s_cnt.get(r['Sector'], 0) >= 3: continue
        top_10.append(r)
        s_cnt[r['Sector']] = s_cnt.get(r['Sector'], 0) + 1
        if len(top_10) >= TARGET_POSITIONS: break

    # 4. 等權重資金分配
    allocation_per_stock = PORTFOLIO_CAPITAL / max(len(top_10), 1)
    
    matrix = []
    headers = ["Ticker", "所屬板塊", "V100評分", "大師決策", "量價狀態分析", "RS動能", "ROE護城河", "Rule of 40", "20EMA乖離", "當前價格", "🛑 破位止損線", "💰 應買股數", "倉位佔比", "更新時間"]
    
    matrix.append([f"V100 (動態輪動版)", f"核心心法: 不主動止盈 / 20均線企穩狙擊", ""] + [""] * 11)
    matrix.append(headers)
    
    for i, r in enumerate(top_10):
        shares = math.floor(allocation_per_stock / (r['Price'] * 100)) * 100
        actual_cost = shares * r['Price']
        weight_pct = (actual_cost / PORTFOLIO_CAPITAL) * 100
        
        matrix.append([
            r['Ticker'], r['Sector'], f"{round(r['Score'], 1)}", 
            r['Action'], r['Msg'], f"{round(r['RS'], 1)}", r['ROE'], r['Rule40'], 
            r['Dist20'], f"¥{round(r['Price'], 2)}", f"¥{round(r['StopLoss'], 2)}", 
            f"{shares:,} 股", f"{round(weight_pct, 2)}%", update_time
        ])

    print(f"📤 正在推送 V100 輪動策略數據至 Google Sheets...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200:
        print("✅ V100 數據已成功推送！完美的頂級交易系統。")
    else:
        print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_super_growth_a()
