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
# 1. 系統配置中心 (V112 先勝後戰・形態學突破版)
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"
TARGET_SHEET = "HK_Super"

PORTFOLIO_CAPITAL = 1_000_000  
TARGET_POSITIONS = 10
AVAILABLE_CAPITAL = PORTFOLIO_CAPITAL * 0.95 
TARGET_VALUE_PER_STOCK = AVAILABLE_CAPITAL / TARGET_POSITIONS 

GURU_LIST_HK = [
    "0700.HK", "9988.HK", "3690.HK", "1810.HK", "1211.HK", "2015.HK", "9868.HK", "9866.HK", 
    "0981.HK", "1347.HK", "0285.HK", "6618.HK", "9999.HK", "0883.HK", "0857.HK", "0386.HK", 
    "0941.HK", "0762.HK", "0728.HK", "1088.HK", "1928.HK", "2020.HK", "6690.HK", "6862.HK",
    "2318.HK", "0388.HK", "1299.HK", "2382.HK", "0293.HK", "1024.HK", "9626.HK",
    "0868.HK", "3800.HK", "2899.HK", "3993.HK", "0020.HK", "1929.HK", "6049.HK", "0772.HK", 
    "1516.HK", "2269.HK", "2359.HK", "6608.HK", "9961.HK", "0268.HK", "0175.HK", "9618.HK",
    "9888.HK", "0992.HK", "1093.HK", "1177.HK", "2331.HK", "0322.HK", "0522.HK", "0836.HK",
    "0669.HK", "0151.HK", "6606.HK", "9992.HK", "9633.HK", "0867.HK", "0316.HK", "1997.HK",
    "0293.HK", "0881.HK", "2313.HK", "0780.HK", "1088.HK", "1919.HK", 
    "1072.HK", "1133.HK", "0005.HK", "2618.HK", "1833.HK" 
]

def get_ret(series, days):
    if series is None or len(series) < days + 1: return 0.0
    val = float(series.iloc[-(days+1)])
    return (float(series.iloc[-1]) / val) - 1 if val != 0 else 0.0

def fetch_info_hk(t):
    ticker = yf.Ticker(t)
    for i in range(2):
        try:
            time.sleep(random.uniform(0.1, 0.2))
            info = ticker.info
            return t, {
                'sector': str(info.get('sector', 'Unknown')),
                'industry': str(info.get('industry', 'Unknown')),
                'returnOnEquity': info.get('returnOnEquity', 0),
                'revenueGrowth': info.get('revenueGrowth', 0),
                'operatingMargins': info.get('operatingMargins', 0)
            }
        except: time.sleep(0.5)
    return t, {}

# ==========================================
# 3. 核心量化模型 V112 (形態學 + VWAP)
# ==========================================
def run_super_growth_hk_v112():
    update_time = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
    universe = list(set(GURU_LIST_HK))
    print("\n" + "="*60)
    print(f"🚀 [港股 動量矩陣 V112] 啟動 | 先勝後戰 (紅黑線突破 & VWAP回踩)")

    print("⏳ 掃描個股多維度報酬率與籌碼形態 (VWAP, H20, H60)...")
    hist_all = yf.download(universe, period="2y", progress=False, threads=False)
    close_df, vol_df, high_df, low_df = hist_all['Close'], hist_all['Volume'], hist_all['High'], hist_all['Low']
    
    tech_pool = {}
    for t in universe:
        if t not in close_df.columns or t not in vol_df.columns: continue
        c, v, h, l = close_df[t].dropna(), vol_df[t].dropna(), high_df[t].dropna(), low_df[t].dropna()
        if len(c) < 252: continue 
        
        p = float(c.iloc[-1])
        m20, m50 = float(c.tail(20).mean()), float(c.tail(50).mean())
        
        avg_vol_10 = float(v.tail(10).mean())
        if p < 1.0 or (avg_vol_10 * p) < 10_000_000: continue 
        if p < m50: continue # 依然嚴守長期趨勢防線

        # 🎯 V112 形態學核心：紅線 (H20頸線) 與 黑線 (H60前高)
        # 故意 .shift(1) 拿掉今天，代表「過去的阻力線」
        red_line_h20 = float(h.shift(1).tail(20).max())
        black_line_h60 = float(h.shift(1).tail(60).max())
        
        # 🎯 V112 籌碼核心：計算 20日 VWAP (成交量加權平均價 - 對標 MU 圖表)
        typical_price = (h + l + c) / 3
        vwap_20 = float((typical_price * v).tail(20).sum() / v.tail(20).sum())
        
        dist_vwap = ((p - vwap_20) / vwap_20) * 100
        dist_red = ((p - red_line_h20) / red_line_h20) * 100
        dist_black = ((p - black_line_h60) / black_line_h60) * 100

        vr = float(v.iloc[-1]) / float(v.tail(50).mean()) if float(v.tail(50).mean()) > 0 else 1.0

        ret_1m = get_ret(c, 21) * 100
        ret_6m = get_ret(c, 126) * 100
        ret_1y = get_ret(c, 252) * 100

        tech_pool[t] = {
            "P": p, "VR": vr, 
            "VWAP20": vwap_20, "DistVWAP": dist_vwap, 
            "DistRed": dist_red, "DistBlack": dist_black,
            "Ret_1M": ret_1m, "Ret_6M": ret_6m, "Ret_1Y": ret_1y,
            "Spark": ",".join([str(round(val, 2)) for val in c.tail(126).tolist()]) # 顯示半年趨勢抓形態
        }

    if not tech_pool: 
        print("⚠️ 查無符合標的。")
        return

    rank_1m = (pd.Series({t: d['Ret_1M'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()
    rank_6m = (pd.Series({t: d['Ret_6M'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()
    rank_1y = (pd.Series({t: d['Ret_1Y'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()

    # 長線多頭過濾
    filtered_tech_pool = {t: d for t, d in tech_pool.items() if rank_6m.get(t, 0) >= 60 or rank_1y.get(t, 0) >= 60}

    print(f"⏳ 拉取基本面 (共 {len(filtered_tech_pool)} 檔長線多頭標的)...")
    infos = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        for t, info in executor.map(fetch_info_hk, list(filtered_tech_pool.keys())):
            if info: infos[t] = info

    all_cands = []
    for t, data in filtered_tech_pool.items():
        info = infos.get(t, {})
        sec, ind = info.get('sector'), info.get('industry')
        roe = (info.get('returnOnEquity') or 0) * 100
        rule_of_40 = (info.get('revenueGrowth') or 0) * 100 + (info.get('operatingMargins') or 0) * 100
        fund_score = (40 if rule_of_40 > 40 else (20 if rule_of_40 > 20 else 0)) + (30 if roe > 15 else (15 if roe > 8 else 0))
        
        r1m, r6m, r1y = rank_1m.get(t, 0), rank_6m.get(t, 0), rank_1y.get(t, 0)
        dist_vwap, dist_red, dist_black, vr = data['DistVWAP'], data['DistRed'], data['DistBlack'], data['VR']
        
        tech_score = (r6m * 0.4) + (r1y * 0.3) + (r1m * 0.2)
        
        # ==========================================
        # 🎯 V112「先勝後戰」戰術決策引擎
        # ==========================================
        if dist_vwap < -3.0: 
            action = f"✂️破線(VWAP {dist_vwap:+.1f}%)"
            tech_score *= 0.3 # 跌破主力成本線，強制斬首
            
        elif dist_black > 0 and vr > 1.2:
            action = f"🚀黑線突破(+量)"
            tech_score += 25 # 戰略勝利 (突破60日前高)
            
        elif dist_red > 0 and vr > 1.2:
            action = f"🔥紅線突破(+量)"
            tech_score += 20 # 戰術勝利 (突破20日頸線)
            
        elif 0 <= dist_vwap <= 3.0 and vr < 0.8:
            action = f"🎯先勝回踩(量縮)"
            tech_score += 25 # 最完美的「後戰」：突破後縮量回踩 VWAP 成本線 (對標 MU 走勢)
            
        elif dist_vwap > 8.0: 
            action = f"👀過熱(VWAP {dist_vwap:+.1f}%)" 
            
        else: 
            action = f"🛡️均線震盪(等方向)"

        total_score = fund_score + tech_score
        
        price = data['P']
        raw_shares = TARGET_VALUE_PER_STOCK / price
        target_shares = max(100, round(raw_shares / 100) * 100)

        all_cands.append({
            "Ticker": t, "Sector": sec, "Industry": ind[:10], "Score": total_score, "Action": action, 
            "Price": price, "DistVWAP": dist_vwap, "DistRed": dist_red,
            "R1M": round(r1m, 0), "R6M": round(r6m, 0), "R1Y": round(r1y, 0),
            "TargetShares": target_shares,
            "Trend": f'=SPARKLINE({{{data["Spark"]}}}, {{"charttype","line";"color","black"}})'
        })

    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_10, sec_cnt = [], {}
    for r in all_cands:
        s = r['Sector']
        if sec_cnt.get(s, 0) >= 4: continue 
        top_10.append(r)
        sec_cnt[s] = sec_cnt.get(s, 0) + 1
        if len(top_10) >= TARGET_POSITIONS: break
    
    # 🎯 輸出矩陣：加入「紅線距離」與「VWAP乖離」等專業籌碼欄位
    headers_col = ["Ticker", "Industry", "Last Price", "半年走勢形態", "6M Rank", "1Y Rank", "紅線距離(頸線)", "VWAP乖離(籌碼)", "操盤指令(先勝後戰)", "綜合評分", "應持有股數", "更新時間"]
    
    matrix = [[f"Momentum Portfolio V112 (先勝後戰・形態學突破版)", f"{update_time}", ""] + [""] * 9, headers_col]
    
    for i, r in enumerate(top_10):
        r6m_str = f"{int(r['R6M'])} 🔥" if r['R6M'] >= 90 else f"{int(r['R6M'])}"
        r1y_str = f"{int(r['R1Y'])} 🔥" if r['R1Y'] >= 90 else f"{int(r['R1Y'])}"

        # 將距離轉為易讀的狀態 (負數代表還沒突破，正數代表已突破)
        red_status = f"已突破 (+{r['DistRed']:.1f}%)" if r['DistRed'] > 0 else f"壓制中 ({r['DistRed']:.1f}%)"

        matrix.append([
            f"👑 {r['Ticker']}" if i < 3 else r['Ticker'], r['Industry'], 
            f"{round(r['Price'], 2)}", r['Trend'], 
            r6m_str, r1y_str, 
            red_status, f"{r['DistVWAP']:+.1f}%",
            r['Action'], f"{round(r['Score'], 1)}", r['TargetShares'], update_time
        ])

    print("📤 推送 V112 形態學矩陣至 Google Sheets...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200: print("✅ V112 數據推送成功！")
    else: print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_super_growth_hk_v112()
