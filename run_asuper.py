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
# 1. 系統配置中心 (V99 實盤級等權重策略)
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"
TARGET_SHEET = "A_Super" 
PORTFOLIO_CAPITAL = 1000000  # 模擬總資金：100萬人民幣
TARGET_POSITIONS = 10        # 嚴格限制 10 檔持倉 (每檔 10% 等權重)

# 🚀 對標美股持倉的 A股映射池 (嚴選 30 檔護城河與算力龍頭)
GURU_LIST_A =[
    # 基礎設施/液冷/電力 (對標 VRT, PWR)
    "300408.SZ", "300308.SZ", "600487.SS", "000977.SZ", "601138.SS", "300274.SZ",
    # 高毛利軟體/SaaS/網路安全 (對標 OKTA, NTNX, DUOL)
    "688111.SS", "300033.SZ", "300496.SZ", "600588.SS", "300059.SZ", "688036.SS",
    # 醫療壟斷/剛需 (對標 LLY)
    "600276.SS", "300760.SZ", "603259.SS", "600436.SS",
    # 金融/交易所/印鈔機防禦 (對標 V, NDAQ)
    "600036.SS", "601318.SS", "600519.SS", "600900.SS", "000858.SZ", "601166.SS",
    # 困境反轉/平台/政策支持 (對標 FSLR, ROKU)
    "300750.SZ", "002594.SZ", "600690.SS", "000333.SZ", "601899.SS", "002415.SZ"
]

def get_universe_a(): return list(set(GURU_LIST_A))

# ==========================================
# 2. 數據獲取引擎 (新增 ROE 與 Rule of 40 參數)
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
                    'returnOnEquity': info.get('returnOnEquity', 0), # ROE 護城河指標
                    'marketCap': info.get('marketCap', 0)
                }
        except: time.sleep(0.3)
    return t, {}

def get_ret(series, days):
    if series is None or len(series) < days + 1: return 0.0
    val = float(series.iloc[-(days+1)])
    return (float(series.iloc[-1]) / val) - 1 if val != 0 else 0.0

# ==========================================
# 3. 核心量化模型 V99
# ==========================================
def run_super_growth_a():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = get_universe_a()
    print("\n" + "="*60)
    print(f"🚀 [A股極致優化 V99] 啟動 | 載入等權重倉位與 ROE/Rule 40 引擎...")

    # 1. 宏觀環境檢測
    try:
        csi = yf.download("000300.SS", period="6mo", progress=False)['Close'].dropna()
        csi_vol = float(csi.pct_change().dropna().tail(20).std() * np.sqrt(252) * 100)
    except: csi_vol = 20.0

    # 2. 技術面掃描 (只留 50MA 之上的強勢股)
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
            if p < m50: continue # 嚴格過濾：跌破 50MA 直接淘汰
            
            ema20 = float(c.ewm(span=20, adjust=False).mean().iloc[-1])
            dist_20ema = ((p - ema20) / ema20) * 100
            
            rs_raw = (get_ret(c, 21)*0.4) + (get_ret(c, 63)*0.4) + (get_ret(c, 126)*0.2)
            vol_50d_avg = float(v.tail(50).mean())
            is_vdu = float(v.tail(3).mean()) < (vol_50d_avg * 0.7)
            
            tech_pool[t] = {
                "P": p, "Dist20": dist_20ema, "RS_Raw": rs_raw,
                "VR": float(v.iloc[-1]) / vol_50d_avg if vol_50d_avg > 0 else 1.0, 
                "Is_VDU": is_vdu, "Stop_Loss": m50
            }
        except: continue

    # 3. 基本面護城河掃描 (SaaS 看 Rule 40，藍籌看 ROE)
    infos = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        for t, info in executor.map(fetch_info_a, list(tech_pool.keys())):
            if info: infos[t] = info

    rs_ranks = (pd.Series({t: d['RS_Raw'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()
    all_cands = []
    
    for t, data in tech_pool.items():
        info, rs = infos.get(t, {}), rs_ranks.get(t, 0)
        
        # 📌 護城河評分系統 (Deep Fundamental Engine)
        op_margin = info.get('operatingMargins') or 0
        rev_g = info.get('revenueGrowth') or 0
        roe = info.get('returnOnEquity') or 0
        
        # Rule of 40 (SaaS/軟體估值法則：成長率 + 利潤率 > 40%)
        rule_of_40 = (op_margin + rev_g) * 100
        
        fund_score = 0
        if roe > 0.15: fund_score += 15       # 高 ROE 印鈔機
        if rule_of_40 > 30: fund_score += 15  # 接近 Rule of 40 的高增長高毛利
        
        # 總分 = 60% 動能強度 + 40% 護城河質量
        score = (rs * 0.6) + fund_score
        
        # 📌 買點決策與大師指引
        dist = data['Dist20']
        if dist > 5.5:
            action, msg = "👀 抱緊/觀望", f"乖離偏高 (+{round(dist,1)}%)"
            score *= 0.85 # 懲罰追高
        elif -2.0 <= dist <= 2.5 and data['Is_VDU']:
            action, msg = "🎯 滿倉狙擊", f"完美回踩縮量"
            score *= 1.25 # 極致獎勵均線回踩買點
        else:
            action, msg = "📈 趨勢延續", f"乖離合理 ({round(dist,1)}%)"
            
        all_cands.append({
            "Ticker": t, "Sector": info.get('sector', 'Unknown')[:10], 
            "Score": score, "Action": action, "Msg": msg, "RS": rs,
            "ROE": f"{round(roe*100, 1)}%", "Rule40": f"{round(rule_of_40, 1)}", 
            "Dist20": f"{round(dist, 1)}%", "Vol": f"{round(data['VR'], 2)}x", 
            "Price": data['P'], "StopLoss": data['Stop_Loss']
        })

    # 4. 板塊分散與 10檔極致精選 (對標截圖)
    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_10, s_cnt = [], {}
    for r in all_cands:
        # 單一板塊最多 3 檔，實現 Risk Parity
        if s_cnt.get(r['Sector'], 0) >= 3: continue
        top_10.append(r)
        s_cnt[r['Sector']] = s_cnt.get(r['Sector'], 0) + 1
        if len(top_10) >= TARGET_POSITIONS: break

    # 5. 💰 等權重倉位管理系統 (Position Sizing Calculator)
    # 將資金平分為 10 份 (每份 10 萬)
    allocation_per_stock = PORTFOLIO_CAPITAL / max(len(top_10), 1)
    
    matrix = []
    # 設定表頭 (加入建議買入股數與倉位)
    headers = ["Ticker", "所屬板塊", "V99評分", "大師操作指引", "量價狀態", "RS動能", "ROE(護城河)", "Rule of 40", "20EMA乖離", "當前價格", "🛑 50MA防守", "💰 建議買入股數", "倉位佔比", "更新時間"]
    
    m_status = f"CSI波幅:{round(csi_vol,1)} | 策略: 10檔等權重 | 總資金: ¥{PORTFOLIO_CAPITAL:,}"
    matrix.append([f"V99 (實盤等權重版)", f"環境: {m_status}", ""] + [""] * 11)
    matrix.append(headers)
    
    for i, r in enumerate(top_10):
        # 計算買入股數 (A股必須是 100 股的整數倍)
        shares = math.floor(allocation_per_stock / (r['Price'] * 100)) * 100
        actual_cost = shares * r['Price']
        weight_pct = (actual_cost / PORTFOLIO_CAPITAL) * 100
        
        matrix.append([
            f"🎯 {r['Ticker']}" if "狙擊" in r['Action'] else r['Ticker'], 
            r['Sector'], f"{round(r['Score'], 1)}", r['Action'], r['Msg'], 
            f"{round(r['RS'], 1)}", r['ROE'], r['Rule40'], r['Dist20'], 
            f"¥{round(r['Price'], 2)}", f"¥{round(r['StopLoss'], 2)}", 
            f"{shares:,} 股", f"{round(weight_pct, 2)}%", update_time
        ])

    # 6. 推送至 Google Sheets
    print(f"📤 正在推送 {len(top_10)} 檔精選標的與倉位建議...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200:
        print("✅ V99 等權重策略數據已成功推送！")
    else:
        print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_super_growth_a()
