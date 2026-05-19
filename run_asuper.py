import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import requests
import warnings
import time
import random
from concurrent.futures import ThreadPoolExecutor

warnings.filterwarnings('ignore')

# ==========================================
# 1. 系統配置中心 (V90 槓鈴策略配置)
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"
TARGET_SHEET = "A_Super" 
YTD_BASE_DATE = "2023-12-31"

# 🚀 大神邏輯 A股重倉池 (AI基礎設施 + 高毛利軟體 + 絕對防禦護城河 + 困境反轉)
GURU_LIST_A =[
    # 基礎設施/算力賣水人 (對標 VRT, PWR)
    "300308.SZ", "601138.SS", "000977.SZ", "603019.SS", "002837.SZ", "600487.SS", "002475.SZ",
    # 高毛利軟體/SaaS/金融數據 (對標 NTNX, OKTA, DUOL)
    "688111.SS", "300033.SZ", "300059.SZ", "600845.SS", "600536.SS", "300496.SZ", "600588.SS",
    # 絕對防禦/高毛利印鈔機/醫療剛需 (對標 V, NDAQ, LLY)
    "600519.SS", "600276.SS", "300760.SZ", "600900.SS", "601985.SS", "600036.SS", "601166.SS", "000858.SZ", "603259.SS",
    # 困境反轉/出海/政策底 (對標 FSLR, ROKU)
    "300274.SZ", "300750.SZ", "002594.SZ", "600690.SS", "000333.SZ", "601899.SS", "601689.SS"
]

EXCLUDED =['Real Estate', 'REIT'] # 放寬銀行與公用事業，因為它們是防禦核心

def get_universe_a(): return list(set(GURU_LIST_A))

# ==========================================
# 2. 輔助函數
# ==========================================
def fetch_info_a(t):
    ticker = yf.Ticker(t)
    for i in range(2):
        try:
            time.sleep(random.uniform(0.1, 0.3))
            info = ticker.info
            if info and 'industry' in info:
                # 抓取營業利潤率與基本資料
                return t, {
                    'industry': str(info.get('industry', 'Unknown')).replace('\t', ''),
                    'sector': str(info.get('sector', 'Unknown')),
                    'operatingMargins': info.get('operatingMargins', 0),
                    'revenueGrowth': info.get('revenueGrowth', 0),
                    'marketCap': info.get('marketCap', 0)
                }
        except: time.sleep(0.5)
    return t, {}

def get_ret(series, days):
    if series is None or len(series) < days + 1: return 0.0
    val = float(series.iloc[-(days+1)])
    if val == 0: return 0.0
    return (float(series.iloc[-1]) / val) - 1

# ==========================================
# 3. 核心量化模型 V90 (大神實盤邏輯升級版)
# ==========================================
def run_super_growth_a():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = get_universe_a()
    print("\n" + "="*60)
    print(f"🚀 [A股超級策略 V90] 啟動 | 載入高毛利防禦與 20EMA 乖離率偵測...")

    # 1. 抓取大盤與宏觀引擎
    try:
        m_list =["000300.SS", "CNY=X", "BNO"]
        m_data = yf.download(m_list, period="1y", progress=False, threads=False)['Close'].ffill()
        csi = m_data['000300.SS'].dropna()
        curr_csi, ma20_csi = float(csi.iloc[-1]), float(csi.tail(20).mean())
        csi_vol = float(csi.pct_change().dropna().tail(20).std() * np.sqrt(252) * 100)
    except: curr_csi, ma20_csi, csi_vol = 3000.0, 3000.0, 20.0

    # 2. 技術面掃描 (引入 20EMA 與乖離率 Dist 控制買點)
    print("⏳ 正在掃描A股技術面，尋找均線多頭且乖離合理的標的...")
    hist_all = yf.download(universe, period="2y", progress=False, threads=False)
    if hist_all.empty: return
        
    close_df, vol_df, high_df, low_df = hist_all['Close'], hist_all['Volume'], hist_all['High'], hist_all['Low']
    tech_pool, perfect_tickers = {}, []
    
    for t in universe:
        try:
            if t not in close_df.columns: continue
            c, h, l, v = close_df[t].dropna(), high_df[t].dropna(), low_df[t].dropna(), vol_df[t].dropna()
            p = float(c.iloc[-1])
            if len(c) < 150 or p < 1.0 or v.tail(10).mean() < 1000000: continue
            
            # 計算均線系統
            m20, m50, m200 = float(c.tail(20).mean()), float(c.tail(50).mean()), float(c.tail(200).mean())
            ema20 = float(c.ewm(span=20, adjust=False).mean().iloc[-1])
            
            # 乖離率 (Dist from 20EMA)
            dist_20ema = ((p - ema20) / ema20) * 100
            
            # 趨勢過濾：股價必須在 50MA 之上，否則視為破位
            if p < m50: continue 
            if p > m20 > m50 > m200: perfect_tickers.append(t)
            
            # 基礎 RS 分數與 VCP 計算
            rs_raw = (get_ret(c, 21)*0.4) + (get_ret(c, 63)*0.4) + (get_ret(c, 126)*0.2)
            vol_50d_avg = float(v.tail(50).mean())
            is_vdu = float(v.tail(3).mean()) < (vol_50d_avg * 0.6)
            
            spark = ",".join([str(round(val, 2)) for val in c.tail(60).tolist()])
            
            tech_pool[t] = {
                "P": p, "EMA20": ema20, "Dist20": dist_20ema,
                "VR": float(v.iloc[-1]) / vol_50d_avg if vol_50d_avg > 0 else 1.0, 
                "RS_Raw": rs_raw, "Spark": spark,
                "Is_VDU": is_vdu, "Stop_Loss": m50  # 以 50MA 作為機構最後防線
            }
        except: continue

    # 3. 獲取基本面 (重構：高毛利與印鈔能力檢驗)
    print("⏳ 正在拉取基本面，篩選高毛利印鈔機...")
    infos = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        for t, info in executor.map(fetch_info_a, list(tech_pool.keys())):
            if info: infos[t] = info

    # 4. 評分與策略操作邏輯打磨 (V90 核心)
    rs_ranks = (pd.Series({t: d['RS_Raw'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()
    all_cands = []
    
    for t, data in tech_pool.items():
        info, rs = infos.get(t, {}), rs_ranks.get(t, 0)
        if rs < 60: continue # 弱勢股直接淘汰
        
        ind, sec = info.get('industry', 'Unknown'), info.get('sector', 'Unknown')
        if any(ex.lower() in ind.lower() for ex in EXCLUDED): continue
        
        # 📌 策略一：高毛利至上 (Margin First)
        op_margin = info.get('operatingMargins') or 0
        rev_g = info.get('revenueGrowth') or 0
        
        fund_score = 0
        if op_margin > 0.15: fund_score += 15  # 毛利大於 15% 加大分
        elif op_margin > 0.05: fund_score += 5
        if rev_g > 0: fund_score += (rev_g * 10)
        
        # 總分 = 動能 (70%) + 基本面護城河 (30%)
        score = (rs * 0.7) + fund_score
        
        # 📌 策略二：乖離率買點控制 (Dist 20EMA)
        dist = data['Dist20']
        if dist > 6.0:
            action, msg = "👀觀望/抱緊", f"乖離過大 (+{round(dist,1)}%)"
            score *= 0.8 # 懲罰追高
        elif -3.0 <= dist <= 1.5 and data['Is_VDU']:
            action, msg = "🎯回踩狙擊", f"貼近20EMA且量縮"
            score *= 1.2 # 獎勵絕佳買點
        elif dist < -4.0:
            action, msg = "⏳等回穩", f"跌破均線深測"
        else:
            action, msg = "📈多頭延續", f"乖離合理 ({round(dist,1)}%)"

        mkt_cap = info.get('marketCap', 0) / 1e9 
        sl_pct = ((data['Stop_Loss'] - data['P']) / data['P']) * 100
        
        all_cands.append({
            "Ticker": t, "Sector": sec[:10], "Industry": ind[:12], "Score": score, 
            "Action": action, "Msg": msg,
            "Trend": f'=SPARKLINE({{{data["Spark"]}}}, {{"charttype","line";"linewidth",2;"color","red"}})',
            "RS": rs, "Margin": f"{round(op_margin*100, 1)}%", "Dist20": f"{round(dist, 1)}%",
            "Vol": f"{round(data['VR'], 2)}x", "Price": f"¥{round(data['P'], 2)}", 
            "Mkt": f"¥{round(mkt_cap, 1)}B ", "StopLoss": f"¥{round(data['Stop_Loss'], 2)} ({round(sl_pct,1)}%)"
        })

    # 📌 策略三：極致的板塊分散 (Sector Parity)
    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_15, s_cnt, i_cnt = [], {}, {}
    for r in all_cands:
        # 單一板塊不超過 3 檔，單一行業不超過 2 檔
        if s_cnt.get(r['Sector'], 0) >= 3 or i_cnt.get(r['Industry'], 0) >= 2: continue
        top_15.append(r)
        s_cnt[r['Sector']] = s_cnt.get(r['Sector'], 0) + 1
        i_cnt[r['Industry']] = i_cnt.get(r['Industry'], 0) + 1
        if len(top_15) >= 15: break

    # 5. 大盤防守對沖 (護城河指標)
    hedge_ticker = f"🛡️ 510300.SS (CSI 300)"
    hedge_action = "🚨 建議加強防禦" if csi_vol > 22.0 or curr_csi < ma20_csi else "💤 宏觀平穩"
    hedge_row = [hedge_ticker, "大盤保險", "N/A", hedge_action, "滬深300 波幅指引", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", update_time]

    # 6. 輸出格式化至 Google Sheets
    headers = ["Ticker", "Industry", "綜合評分", "大師操作指引", "策略理由", "60日趨勢", "RS強度", "營業利潤率(護城河)", "20EMA乖離率", "量比", "當前價格", "市值", "50MA防守位", "持倉狀態", "更新時間"]
    
    m_status = f"完美多頭:{len(perfect_tickers)}隻 | CSI波幅:{round(csi_vol,1)} | 策略: 槓鈴防禦+基礎設施"
    row1 = [f"V90 Pro (Guru實盤對標版)", f"宏觀狀態: {m_status}", ""] + [""] * 12
    
    matrix = [row1, headers]
    for i, r in enumerate(top_15):
        matrix.append([
            f"👑 {r['Ticker']}" if i < 3 else r['Ticker'], r['Industry'], f"{round(r['Score'], 1)}", 
            r['Action'], r['Msg'], r['Trend'], 
            f"{round(r['RS'], 1)}", r['Margin'], r['Dist20'], r['Vol'], 
            r['Price'], r['Mkt'], r['StopLoss'], "✅ 持有/追蹤", update_time
        ])
    matrix.append(hedge_row)

    print("📤 正在推送 V90 數據到 Google Sheets...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200:
        print("✅ V90 數據已成功推送！")
    else:
        print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_super_growth_a()
