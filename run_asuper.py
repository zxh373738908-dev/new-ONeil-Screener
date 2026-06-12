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
# 1. 系統配置中心 (V120 動態止盈與大換血版)
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"
TARGET_SHEET = "A_Super" 
PORTFOLIO_CAPITAL = 1000000  # 總資金：100萬人民幣
TARGET_POSITIONS = 10        # 精準 10 檔等權重

# 🚀 V120 全新股票池：軍工/衛星/存儲/高端消費
GURU_LIST_A =[
    # 存儲晶片/半導體週期 (對標 MU 美光)
    "603986.SS", "301308.SZ", "688525.SS", "000021.SZ",
    # 低軌衛星/商業航太/通訊 (對標 IRDM 銥星通訊)
    "601698.SS", "001270.SZ", "688292.SS", "600118.SS",
    # 國防軍工/航空發動機材料 (對標 ATI 特種材料)
    "600893.SS", "600862.SS", "688122.SS", "000768.SZ",
    # 高端消費/免稅/奢華旅遊 (對標 VIK 維京遊輪)
    "601888.SS", "603099.SS", "600258.SS",
    # 絕對核心老將 (對標未平倉的基礎設施 PWR 等)
    "300308.SZ", "600487.SS", "300408.SZ", "603259.SS"
]

def get_universe_a(): return list(set(GURU_LIST_A))

# ==========================================
# 2. 獲取基本面 (護城河與估值)
# ==========================================
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
                    'trailingPE': info.get('trailingPE', 0)
                }
        except: time.sleep(0.3)
    return t, {}

def get_ret(series, days):
    if series is None or len(series) < days + 1: return 0.0
    val = float(series.iloc[-(days+1)])
    return (float(series.iloc[-1]) / val) - 1 if val != 0 else 0.0

# ==========================================
# 3. 核心量化模型 V120 
# ==========================================
def run_super_growth_a():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = get_universe_a()
    print("\n" + "="*65)
    print(f"🚀 [A股 V120 終極型態] 啟動 | 載入「10EMA動能衰竭止盈」與「新週期換血」引擎...")

    # 📌 1. 大盤 Beta 對沖偵測
    try:
        csi = yf.download("000300.SS", period="6mo", progress=False)['Close'].dropna()
        curr_csi, ma20_csi = float(csi.iloc[-1]), float(csi.tail(20).mean())
        need_hedge = curr_csi < ma20_csi 
    except:
        need_hedge, curr_csi = False, 3500.0

    # 📌 2. 技術面與動能掃描 (引入 10EMA 止盈線與高點回撤)
    hist_all = yf.download(universe, period="1y", progress=False, threads=False)
    if hist_all.empty: return
    close_df, vol_df = hist_all['Close'], hist_all['Volume']
    
    tech_pool = {}
    for t in universe:
        try:
            c, v = close_df[t].dropna(), vol_df[t].dropna()
            p = float(c.iloc[-1])
            if len(c) < 100 or p < 1.0: continue
            
            # 均線系統
            m50 = float(c.tail(50).mean())
            ema10 = float(c.ewm(span=10, adjust=False).mean().iloc[-1]) # 極短期動能線
            ema20 = float(c.ewm(span=20, adjust=False).mean().iloc[-1])
            
            dist_20ema = ((p - ema20) / ema20) * 100
            h60 = float(c.tail(60).max())
            drawdown_from_high = ((p - h60) / h60) * 100 # 計算從近期高點回撤多少
            
            rs_raw = (get_ret(c, 21)*0.4) + (get_ret(c, 63)*0.4) + (get_ret(c, 126)*0.2)
            vol_50d_avg = float(v.tail(50).mean())
            is_vdu = float(v.tail(3).mean()) < (vol_50d_avg * 0.7)
            
            tech_pool[t] = {
                "P": p, "Dist20": dist_20ema, "EMA10": ema10, "Stop_Loss": m50,
                "Drawdown": drawdown_from_high, "RS_Raw": rs_raw, "Is_VDU": is_vdu
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
        pe = info.get('trailingPE') or 0
        sec = info.get('sector', 'Unknown')
        
        score = (rs * 0.7) + (roe * 100 * 0.3) # 70% 動能 + 30% 基本面
        
        # 📌 V120 核心決策樹 (對標交割單邏輯)
        p, ema10, dist = data['P'], data['EMA10'], data['Dist20']
        
        if p < data['Stop_Loss']:
            action, msg = "🔪 無情砍倉", "對標 ROKU/ADM: 跌破50MA，立刻止損"
            score *= 0.1 # 強制淘汰出 Top 10
        elif p < ema10 and data['Drawdown'] < -8.0:
            action, msg = "💰 動能止盈", "對標 VRT/FSLR: 高位動能衰竭，落袋為安"
            score *= 0.5 # 大幅降分，讓出資金空間給新股票
        elif dist > 4.5 and p > ema10:
            action, msg = "🚀 讓利潤奔跑", "對標 PWR: 強勢站穩10日線，死抱不賣"
            score *= 1.1 
        elif -2.0 <= dist <= 3.0 and data['Is_VDU']:
            action, msg = "🎯 新週期建倉", "對標 MU/IRDM: 均線企穩，絕佳狙擊點"
            score *= 1.3 # 大幅獎勵建倉點
        else:
            action, msg = "📈 趨勢延續", "乖離合理，安全持有"
            
        all_cands.append({
            "Ticker": t, "Sector": sec[:10], "Score": score, "Action": action, "Msg": msg, 
            "RS": rs, "ROE": f"{round(roe*100, 1)}%", "PE": f"{round(pe, 1)}", 
            "Dist20": f"{round(dist, 1)}%", "Price": p, 
            "Trail_Stop": ema10, "Hard_Stop": data['Stop_Loss']
        })

    # 📌 3. 精選 Top 10 
    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_10, s_cnt = [], {}
    for r in all_cands:
        if s_cnt.get(r['Sector'], 0) >= 3: continue # 單板塊最多3檔
        top_10.append(r)
        s_cnt[r['Sector']] = s_cnt.get(r['Sector'], 0) + 1
        if len(top_10) >= TARGET_POSITIONS: break

    # 計算資金分配
    allocation_per_stock = PORTFOLIO_CAPITAL / max(len(top_10), 1)
    
    matrix = []
    headers = ["Ticker", "板塊/概念", "V120大師指令", "交割單對標邏輯", "RS強度", "ROE護城河", "PE估值", "20EMA乖離", "當前價格", "💰 10EMA 移動止盈", "🛑 50MA 破位止損", "建議買入股數", "倉位佔比", "更新時間"]
    
    m_status = f"大盤對沖: {'🚨 已啟動 (IF做空)' if need_hedge else '💤 未啟動'} | 策略: 動態止盈+換股"
    matrix.append([f"V120 (終極交割單實戰版)", f"環境: {m_status}", ""] + [""] * 11)
    matrix.append(headers)
    
    for r in top_10:
        shares = math.floor(allocation_per_stock / (r['Price'] * 100)) * 100
        actual_cost = shares * r['Price']
        weight_pct = (actual_cost / PORTFOLIO_CAPITAL) * 100
        
        matrix.append([
            r['Ticker'], r['Sector'], r['Action'], r['Msg'], 
            f"{round(r['RS'], 1)}", r['ROE'], r['PE'], r['Dist20'], 
            f"¥{round(r['Price'], 2)}", f"¥{round(r['Trail_Stop'], 2)}", f"¥{round(r['Hard_Stop'], 2)}", 
            f"{shares:,} 股", f"{round(weight_pct, 2)}%", update_time
        ])

    # 宏觀對沖提示
    if need_hedge:
        matrix.append([
            "🛡️ IF主力合約 (或反向ETF)", "宏觀對沖 (Beta=0)", "🚨 做空大盤", 
            "鎖定大盤下行風險，保護多頭部位", "-", "-", "-", "-", 
            f"點數 {round(curr_csi,1)}", "-", "-", "1 口空單", "100%對沖", update_time
        ])

    print(f"📤 正在推送 V120 動態換血陣型至 Google Sheets...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200:
        print("✅ V120 數據已成功推送！準備執行大神的獲利了結與換倉計畫。")
    else:
        print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_super_growth_a()
