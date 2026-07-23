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
# 1. 系統配置中心 (V160 機構調倉計算版)
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"
TARGET_SHEET = "A_Super" 
PORTFOLIO_CAPITAL = 1000000  # 帳戶總資本 100萬人民幣
RESERVE_CASH_PCT = 0.05      # 💰 新增：5% 備用金規則
TARGET_POSITIONS = 10        # 10 檔等權重

# 🚀 V160 股票池史詩級大換血：對標降息受惠/週期擴散
GURU_LIST_A =[
    # 🆕 新增：物流貨運/出行復甦 (對標 JBHT, HST)
    "002352.SZ", # 順豐控股
    "601816.SS", # 京滬高鐵
    "600754.SS", # 錦江酒店
    
    # 🆕 新增：創新藥/生技 (對標 ROIV)
    "688235.SS", # 百濟神州
    "300759.SZ", # 康龍化成
    
    # 🆕 新增：資產管理/券商 (對標 STT)
    "300059.SZ", # 東方財富
    "600030.SS", # 中信証券
    
    # 🆕 新增：特種化工材料 (對標 PRM)
    "600309.SS", # 萬華化學
    "600160.SS", # 巨化股份
    
    # 🆕 新增：軟體安全/衛星 (對標 YOU, VSAT)
    "002439.SZ", # 啟明星辰
    "601698.SS", # 中國衛通
    
    # 🛡️ 保留倖存者：軍工材料、油氣能源、困境反轉 (對標 ATI, TRGP, ROKU)
    "600893.SS", # 航發動力
    "600938.SS", # 中國海油
    "300413.SZ"  # 芒果超媒
]

def get_universe_a(): return list(set(GURU_LIST_A))

def get_ret(series, days):
    if series is None or len(series) < days + 1: return 0.0
    val = float(series.iloc[-(days+1)])
    return (float(series.iloc[-1]) / val) - 1 if val != 0 else 0.0

# ==========================================
# 3. 核心量化模型 V160
# ==========================================
def run_super_growth_a():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = get_universe_a()
    print("\n" + "="*65)
    print(f"📊 [A股 Master Sniper V160] 啟動 | 載入「5%備用金」與「板塊擴散大換血」引擎...")

    hist_all = yf.download(universe, period="1y", progress=False, threads=False)
    if hist_all.empty: return
    close_df, vol_df = hist_all['Close'], hist_all['Volume']
    
    tech_pool = {}
    for t in universe:
        try:
            c, v = close_df[t].dropna(), vol_df[t].dropna()
            p = float(c.iloc[-1])
            if len(c) < 100 or p < 1.0: continue
            
            m50 = float(c.tail(50).mean())
            ema20 = float(c.ewm(span=20, adjust=False).mean().iloc[-1])
            dist_20ema = ((p - ema20) / ema20) * 100
            
            rs_raw = (get_ret(c, 21)*0.4) + (get_ret(c, 63)*0.4) + (get_ret(c, 126)*0.2)
            
            tech_pool[t] = {
                "P": p, "Dist20": dist_20ema, "Stop_Loss": m50, "RS_Raw": rs_raw
            }
        except: continue

    rs_ranks = (pd.Series({t: d['RS_Raw'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()
    all_cands = []
    
    for t, data in tech_pool.items():
        rs = rs_ranks.get(t, 0)
        p, dist = data['P'], data['Dist20']
        
        # 動能極弱或破位直接剔除
        if p < data['Stop_Loss'] or rs < 40: 
            continue
            
        score = rs
        
        # 大師決策邏輯
        if dist > 8.0:
            action, msg = "🚀 讓利潤奔跑", "高位強勢，計算再平衡減碼額度"
        elif 0 <= dist <= 5.0:
            action, msg = "🔥 週期擴散建倉", "對標 JBHT/ROIV: 新週期發動，積極買入"
            score *= 1.2 # 優先買入新週期標的
        else:
            action, msg = "📈 等權重抱緊", "均線附近震盪，維持目標市值"
            
        all_cands.append({
            "Ticker": t, "Score": score, "Action": action, "Msg": msg, 
            "RS": rs, "Dist20": f"{round(dist, 1)}%", "Price": p
        })

    # 精選 Top 10
    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_10 = all_cands[:TARGET_POSITIONS]

    # 💰 V160 核心：機構調倉計算機 (The Rebalance Engine)
    reserve_cash = PORTFOLIO_CAPITAL * RESERVE_CASH_PCT
    investable_capital = PORTFOLIO_CAPITAL - reserve_cash
    target_value_per_stock = investable_capital / max(len(top_10), 1)
    
    matrix = []
    # 完全對標截圖的表頭設計
    headers = ["排名", "代碼", "V160 動量決策", "現價", "🎯 應持有市值", "⚖️ 應持有股份數", "20EMA乖離", "RS強度", "更新時間"]
    
    m_status = f"帳戶資本: ¥{PORTFOLIO_CAPITAL:,} | 備用金(5%): ¥{reserve_cash:,} | 策略: 週期擴散"
    matrix.append([f"動量組合 · 調倉計算表 (V160版)", f"狀態: {m_status}", ""] + [""] * 6)
    matrix.append(headers)
    
    for i, r in enumerate(top_10):
        # 計算應持有股數 (A股必須為 100 的整數倍，向下取整保證不超買)
        target_shares = math.floor(target_value_per_stock / (r['Price'] * 100)) * 100
        actual_target_value = target_shares * r['Price']
        
        matrix.append([
            f"{i+1}", f"👑 {r['Ticker']}", r['Action'], 
            f"¥{round(r['Price'], 2)}", 
            f"¥{round(actual_target_value, 2)}", # 應持有市值
            f"{target_shares:,} 股",            # 應持有股份數
            r['Dist20'], f"{round(r['RS'], 1)}", update_time
        ])

    print(f"📤 正在推送 V160 動量調倉計算表至 Google Sheets...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200:
        print("✅ V160 數據已成功推送！系統已為您計算出精確的調倉股份數。")
    else:
        print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_super_growth_a()
