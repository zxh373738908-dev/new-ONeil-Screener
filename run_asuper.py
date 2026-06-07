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
# 1. 系統配置中心 (V110 市場中性對沖版)
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"
TARGET_SHEET = "A_Super" 
PORTFOLIO_CAPITAL = 1000000  # 模擬總資金：100萬人民幣
TARGET_POSITIONS = 10        # 10檔多頭標的

# 🚨 V110 全新股票池：防禦/實體/農業/彩票 大換血
GURU_LIST_A =[
    # 農業/大宗商品/抗通膨 (對標 ADM)
    "600598.SS", "002714.SZ", "000998.SZ", "600108.SS",
    # 必選消費/成癮性剛需/高定價權 (對標 MNST)
    "605499.SS", "600519.SS", "000858.SZ", "600600.SS",
    # 航空/實體出行/低估值復甦 (對標 DAL)
    "601021.SS", "601111.SS", "600029.SS",
    # 高息券商/金融 (對標 IBKR)
    "300059.SZ", "600030.SS", "600036.SS",
    # 顛覆性彩票股 (對標 QS - 固態電池/前沿科技，高風險)
    "300890.SZ", "688568.SS", "300014.SZ",
    # 絕對核心老將 (對標 PWR, VRT, LLY, FSLR，不主動止盈)
    "300408.SZ", "300308.SZ", "600487.SS", "603259.SS", "600276.SS", "300750.SZ"
]

def get_universe_a(): return list(set(GURU_LIST_A))

# ==========================================
# 2. 獲取基本面 (適配價值股與科技股雙軌制)
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
                    'returnOnEquity': info.get('returnOnEquity', 0),
                    'trailingPE': info.get('trailingPE', 0) # V110 加入估值PE評估
                }
        except: time.sleep(0.3)
    return t, {}

def get_ret(series, days):
    if series is None or len(series) < days + 1: return 0.0
    val = float(series.iloc[-(days+1)])
    return (float(series.iloc[-1]) / val) - 1 if val != 0 else 0.0

# ==========================================
# 3. 核心量化模型 V110 
# ==========================================
def run_super_growth_a():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = get_universe_a()
    print("\n" + "="*65)
    print(f"🚨 [A股 V110 避險基金版] 啟動 | 載入 Market Neutral 對沖與週期切換引擎...")

    # 📌 1. 大盤 Beta 對沖引擎 (對標 MES -8)
    try:
        csi = yf.download("000300.SS", period="6mo", progress=False)['Close'].dropna()
        curr_csi = float(csi.iloc[-1])
        ma20_csi = float(csi.tail(20).mean())
        ma50_csi = float(csi.tail(50).mean())
        csi_vol = float(csi.pct_change().dropna().tail(20).std() * np.sqrt(252) * 100)
        
        # 判斷是否需要 100% 完全對沖 (大盤破位 20MA 或波動劇烈)
        need_hedge = curr_csi < ma20_csi or csi_vol > 22.0
    except:
        need_hedge, curr_csi, csi_vol = False, 3500.0, 20.0

    # 📌 2. 個股技術面與動能掃描
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
            
            tech_pool[t] = {"P": p, "Dist20": dist_20ema, "Dist50": dist_50ma, "RS_Raw": rs_raw, "VR": float(v.iloc[-1]) / vol_50d_avg if vol_50d_avg > 0 else 1.0, "Is_VDU": is_vdu, "Stop_Loss": m50}
        except: continue

    infos = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        for t, info in executor.map(fetch_info_a, list(tech_pool.keys())):
            if info: infos[t] = info

    rs_ranks = (pd.Series({t: d['RS_Raw'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()
    all_cands = []
    
    for t, data in tech_pool.items():
        info, rs = infos.get(t, {}), rs_ranks.get(t, 0)
        
        if rs < 50 or data['Dist50'] < 0: continue # 無情汰弱

        roe = info.get('returnOnEquity') or 0
        pe = info.get('trailingPE') or 0
        sec = info.get('sector', 'Unknown')
        
        fund_score = 0
        if roe > 0.15: fund_score += 15       
        if pe > 0 and pe < 25: fund_score += 10 # 價值股 PE 低於 25 加分 
        
        score = (rs * 0.6) + fund_score
        
        # 📌 V110 決策樹 (加入 QS 彩票股邏輯)
        is_lottery = t in ["300890.SZ", "688568.SS", "300014.SZ"]
        
        dist = data['Dist20']
        if dist > 4.5:
            action, msg = "🚀 讓利潤奔跑", f"對標 PWR: 趨勢強勁 (+{round(dist,1)}%)"
            score *= 1.1
        elif -2.0 <= dist <= 2.5 and data['Is_VDU']:
            action, msg = "🎯 價值回踩", f"對標 DAL/ADM: 20EMA企穩，逢低承接"
            score *= 1.25 
        elif is_lottery:
            action, msg = "🎲 彩票配置", f"對標 QS: 顛覆性科技，嚴控低倉位"
            score *= 1.1 # 確保彩票股有機會入選
        elif dist < -3.0:
            action, msg = "⚠️ 破位風險", f"跌破均線，準備無情平倉"
            score *= 0.6  
        else:
            action, msg = "📈 趨勢延續", f"乖離合理，安全持有"
            
        all_cands.append({
            "Ticker": t, "Sector": sec[:10], "Score": score, "Action": action, 
            "Msg": msg, "RS": rs, "ROE": f"{round(roe*100, 1)}%", "PE": f"{round(pe, 1)}", 
            "Dist20": f"{round(dist, 1)}%", "Price": data['P'], "StopLoss": data['Stop_Loss'],
            "IsLottery": is_lottery
        })

    # 📌 3. 精選 10 檔與資金分配 (含彩票股控管)
    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_10, s_cnt, has_lottery = [], {}, False
    for r in all_cands:
        if s_cnt.get(r['Sector'], 0) >= 3: continue
        if r['IsLottery']:
            if has_lottery: continue # 最多只買1檔彩票股
            has_lottery = True
            
        top_10.append(r)
        s_cnt[r['Sector']] = s_cnt.get(r['Sector'], 0) + 1
        if len(top_10) >= TARGET_POSITIONS: break

    # 計算多頭持倉
    allocation_per_stock = PORTFOLIO_CAPITAL / max(len(top_10), 1)
    
    matrix = []
    headers = ["Ticker/合約", "板塊/類型", "V110決策", "大師對標邏輯", "RS動能", "ROE護城河", "PE估值", "20EMA乖離", "當前價格", "🛑 破位止損", "💰 交易數量", "倉位 / 對沖佔比", "更新時間"]
    
    m_status = f"CSI波幅:{round(csi_vol,1)} | 宏觀對沖: {'🚨 已啟動' if need_hedge else '💤 未觸發'}"
    matrix.append([f"V110 (市場中性與週期對沖版)", f"環境: {m_status}", ""] + [""] * 10)
    matrix.append(headers)
    
    # 📌 4. 寫入多頭股票部位
    for r in top_10:
        # 彩票股強制限縮倉位 (約 7%-8%，對標 QS)
        adj_alloc = allocation_per_stock * 0.75 if r['IsLottery'] else allocation_per_stock
        shares = math.floor(adj_alloc / (r['Price'] * 100)) * 100
        actual_cost = shares * r['Price']
        weight_pct = (actual_cost / PORTFOLIO_CAPITAL) * 100
        
        matrix.append([
            r['Ticker'], "🎲 彩票(高風險)" if r['IsLottery'] else r['Sector'], 
            r['Action'], r['Msg'], f"{round(r['RS'], 1)}", r['ROE'], r['PE'], 
            r['Dist20'], f"¥{round(r['Price'], 2)}", f"¥{round(r['StopLoss'], 2)}", 
            f"{shares:,} 股", f"{round(weight_pct, 2)}%", update_time
        ])

    # 📌 5. 寫入空頭對沖部位 (The MES -8 Equivalent)
    # 假設使用 IF 期指 (合約乘數 300) 或 直接建議做空金額
    if need_hedge:
        # 估算: 1口 IF合約價值大約是 CSI300 * 300。若 CSI300=3500，合約價值約 105萬。
        # 剛好對沖 100萬 的總資金。
        contracts_needed = round(-PORTFOLIO_CAPITAL / (curr_csi * 300))
        if contracts_needed == 0: contracts_needed = -1 # 至少空1口
        hedge_notional = contracts_needed * curr_csi * 300
        hedge_weight = (hedge_notional / PORTFOLIO_CAPITAL) * 100
        
        matrix.append([
            "🛡️ IF主力合約 (或反向ETF)", "系統對沖 (Beta=0)", "🚨 做空大盤", 
            "對標 MES -8: 鎖定Beta風險，僅賺取個股Alpha", "-", "-", "-", "-", 
            f"點數 {round(curr_csi,1)}", "-", f"{contracts_needed} 口空單", 
            f"{round(hedge_weight, 2)}% (100%對沖)", update_time
        ])
    else:
        matrix.append([
            "🛡️ 宏觀對沖", "系統對沖", "💤 暫無風險", 
            "大盤20MA之上且波動平穩，無需對沖", "-", "-", "-", "-", 
            "-", "-", "0 口", "0.00%", update_time
        ])

    print(f"📤 正在推送 V110 對沖組合數據至 Google Sheets...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200:
        print("✅ V110 數據已成功推送！完美的 Market Neutral 對沖陣型部署完畢。")
    else:
        print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_super_growth_a()
