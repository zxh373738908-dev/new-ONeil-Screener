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
# 1. 系統配置中心 (V140 無我輪動與困境反轉版)
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"
TARGET_SHEET = "A_Super" 
PORTFOLIO_CAPITAL = 1000000  
TARGET_POSITIONS = 10  

# 🚀 V140 股票池大換血：加入跌深反彈平台/傳媒股 (ROKU對標)
GURU_LIST_A =[
    # 🔄 ROKU 對標：平台經濟/傳媒互聯網/困境反轉
    "300413.SZ", # 芒果超媒 (串流/內容平台)
    "002027.SZ", # 分眾傳媒 (廣告平台復甦)
    "300059.SZ", # 東方財富 (互聯網券商跌深反彈)
    "600588.SS", # 用友網絡 (SaaS超跌反彈)
    
    # MU / 半導體週期
    "301308.SZ", "688525.SS", "603986.SS",
    # 傳統防禦/剛需/高股息
    "600938.SS", "601088.SS", "603259.SS", "600276.SS",
    # 科技與基礎設施老將 (PWR對標)
    "300308.SZ", "600487.SS", "300408.SZ", "601138.SS"
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
# 3. 核心量化模型 V140
# ==========================================
def run_super_growth_a():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = get_universe_a()
    print("\n" + "="*65)
    print(f"🔄 [A股 Master Sniper V140] 啟動 | 載入「ROKU破底翻買回」與「IRDM預期落空平倉」引擎...")

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
            
            # 分拆短、中、長期動能 (為了抓 ROKU 式底部爆發)
            ret_21 = get_ret(c, 21)
            ret_63 = get_ret(c, 63)
            ret_126 = get_ret(c, 126)
            rs_raw = (ret_21 * 0.4) + (ret_63 * 0.4) + (ret_126 * 0.2)
            
            vol_50d_avg = float(v.tail(50).mean())
            is_vdu = float(v.tail(3).mean()) < (vol_50d_avg * 0.8)
            
            tech_pool[t] = {
                "P": p, "Dist20": dist_20ema, "Dist50": dist_50ma, "Stop_Loss": m50,
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
        
        # 評分權重：動能 + ROE
        score = (rs * 0.7) + (roe * 100 * 0.3)
        
        # 🎯 V140 核心決策樹 (IRDM vs ROKU)
        dist = data['Dist20']
        dist50 = data['Dist50']
        
        # ROKU 邏輯：過去中期弱(Ret63低)，但短期突然爆發(Ret21高)，且剛越過50MA(乖離<5%)
        is_roku_turnaround = data['Ret21'] > data['Ret63'] and 0 < dist50 < 5.0 and rs > 60
        
        # IRDM 邏輯：短期動能突然轉負，且跌破20EMA
        is_irdm_failure = data['Ret21'] < 0 and dist < 0 and data['P'] > data['Stop_Loss']
        
        if is_roku_turnaround:
            action, msg = "🔄 困境反轉", "對標 ROKU: 短期動能爆發，強勢買回/建倉"
            score *= 1.35 # 給予破底翻極高權重！
        elif is_irdm_failure:
            action, msg = "⚡ 預期落空", "對標 IRDM: 動能拖泥帶水，果斷換股"
            score *= 0.5 # 降級，準備踢出 Top 10
        elif data['P'] < data['Stop_Loss']:
            continue # 跌破 50MA 直接無情清洗 (QS邏輯延續)
        elif dist > 8.0:
            action, msg = "🚀 讓利潤奔跑", "高位強勢，抱緊不賣"
        elif -2.5 <= dist <= 1.0 and data['Is_VDU']:
            action, msg = "🎯 狙擊加倉", "縮量回踩20均線，絕佳買點"
        else:
            action, msg = "📈 趨勢延續", "乖離合理，安全持有"
            
        all_cands.append({
            "Ticker": t, "Sector": sec[:10], "Score": score, "Action": action, "Msg": msg, 
            "RS": rs, "ROE": f"{round(roe*100, 1)}%", "Dist20": f"{round(dist, 1)}%", 
            "Price": data['P'], "Hard_Stop": data['Stop_Loss']
        })

    # 📌 精選 Top 10 
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
    headers = ["排名", "代碼", "板塊", "V140 大師指令", "交割單對標邏輯", "RS動能", "ROE護城河", "20EMA乖離", "當前價格", "🛑 50MA 止損線", "建議買入股數", "倉位佔比", "更新時間"]
    
    m_status = f"策略: 無我交易 (預期落空平倉 + 破底翻買回)"
    matrix.append([f"Master Sniper V140 (無我輪動版)", f"更新: {update_time} | 狀態: {m_status}", ""] + [""] * 10)
    matrix.append(headers)
    
    for i, r in enumerate(top_10):
        shares = math.floor(allocation_per_stock / (r['Price'] * 100)) * 100
        actual_cost = shares * r['Price']
        weight_pct = (actual_cost / PORTFOLIO_CAPITAL) * 100
        
        matrix.append([
            f"T{i+1}", f"👑 {r['Ticker']}", r['Sector'], r['Action'], r['Msg'], 
            f"{round(r['RS'], 1)}", r['ROE'], r['Dist20'], 
            f"¥{round(r['Price'], 2)}", f"¥{round(r['Hard_Stop'], 2)}", 
            f"{shares:,} 股", f"{round(weight_pct, 2)}%", update_time
        ])

    print(f"📤 正在推送 V140 無我輪動陣型至 Google Sheets...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200:
        print("✅ V140 數據已成功推送！準備捕捉 ROKU 式的超級困境反轉。")
    else:
        print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_super_growth_a()
