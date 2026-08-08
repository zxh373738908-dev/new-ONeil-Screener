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
# 1. 系統配置中心 (V111 多維度動能矩陣版)
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"
TARGET_SHEET = "HK_Super"

PORTFOLIO_CAPITAL = 1_000_000  
TARGET_POSITIONS = 10
AVAILABLE_CAPITAL = PORTFOLIO_CAPITAL * 0.95 # 5% 備用金
TARGET_VALUE_PER_STOCK = AVAILABLE_CAPITAL / TARGET_POSITIONS 

# 全板塊解禁 (確保科技、半導體、平台股全數在列，捕捉 Tech 回歸)
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
# 3. 核心量化模型 V111
# ==========================================
def run_super_growth_hk_v111():
    update_time = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
    universe = list(set(GURU_LIST_HK))
    print("\n" + "="*60)
    print(f"🚀 [港股 動量矩陣 V111] 啟動 | 多維度動能 (1M/6M/1Y) & 科技回歸")

    print("⏳ 掃描個股多維度報酬率 (1D/1M/6M/1Y)...")
    # 抓取2年數據以確保能計算 1Y (252天) 報酬
    hist_all = yf.download(universe, period="2y", progress=False, threads=False)
    close_df, vol_df = hist_all['Close'], hist_all['Volume']
    
    tech_pool = {}
    for t in universe:
        if t not in close_df.columns or t not in vol_df.columns: continue
        c, v = close_df[t].dropna(), vol_df[t].dropna()
        if len(c) < 252: continue # 必須有足夠長度的歷史資料
        
        p = float(c.iloc[-1])
        m20, m50 = float(c.tail(20).mean()), float(c.tail(50).mean())
        
        avg_vol_10 = float(v.tail(10).mean())
        if p < 1.0 or (avg_vol_10 * p) < 10_000_000: continue 
        if p < m50: continue # 依然嚴守 50MA 長期趨勢防線

        ema20 = float(c.ewm(span=20, adjust=False).mean().iloc[-1])
        dist_20ema = ((p - ema20) / ema20) * 100 
        vr = float(v.iloc[-1]) / float(v.tail(50).mean()) if float(v.tail(50).mean()) > 0 else 1.0

        # 🎯 V111 核心：多時間框架報酬率
        ret_1d = (p / float(c.iloc[-2]) - 1) * 100
        ret_1m = get_ret(c, 21) * 100
        ret_6m = get_ret(c, 126) * 100
        ret_1y = get_ret(c, 252) * 100

        tech_pool[t] = {
            "P": p, "Dist20EMA": dist_20ema, "VR": vr,
            "Ret_1D": ret_1d, "Ret_1M": ret_1m, "Ret_6M": ret_6m, "Ret_1Y": ret_1y,
            "Spark": ",".join([str(round(val, 2)) for val in c.tail(252).tolist()]) # 顯示1Y趨勢
        }

    if not tech_pool: 
        print("⚠️ 查無符合標的。")
        return

    # 🎯 V111 核心：計算全市場 1M / 6M / 1Y 獨立百分位排名 (0-100)
    rank_1m = (pd.Series({t: d['Ret_1M'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()
    rank_6m = (pd.Series({t: d['Ret_6M'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()
    rank_1y = (pd.Series({t: d['Ret_1Y'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()

    # 篩選條件：只要中長線 (6M 或 1Y) 強勢即可進入候選池 (對標 AMD 邏輯)
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
        dist, vr = data['Dist20EMA'], data['VR']
        
        # 🎯 V111 評分引擎：中長期權重極大化，包容短期回檔
        # 給予 6M 最高的權重 (40%)，1Y (30%)，1M (20%)
        tech_score = (r6m * 0.4) + (r1y * 0.3) + (r1m * 0.2)
        
        # AMD / VSAT 買點加分邏輯：長線極強 (>85) 但短線回調跌破 30 -> 完美黃金坑洗盤！
        if (r6m > 85 or r1y > 85) and r1m < 40 and -2 <= dist <= 3:
            tech_score += 25 
        
        if vr > 1.5 and dist > 0: tech_score += 15 
        total_score = fund_score + tech_score
        
        # 操盤指令判定
        if dist < -3.0: action = f"✂️破線({dist:+.1f}%)"
        elif (r6m > 85 or r1y > 85) and r1m < 40 and -2 <= dist <= 3:
            action = f"🎯黃金坑回檔" # 復刻 AMD 買點
            total_score *= 1.3
        elif 0 <= dist <= 3.0: action = f"🎯狙擊({dist:+.1f}%)"
        elif -3.0 <= dist < 0: action = f"🎯加倉({dist:+.1f}%)"
        elif dist > 8.0: action = f"👀觀望({dist:+.1f}%)" 
        else: action = f"🛡️續抱({dist:+.1f}%)"

        price = data['P']
        raw_shares = TARGET_VALUE_PER_STOCK / price
        target_shares = max(100, round(raw_shares / 100) * 100)

        all_cands.append({
            "Ticker": t, "Sector": sec, "Industry": ind[:10], "Score": total_score, "Action": action, 
            "Price": price, "1D": data['Ret_1D'], "1M": data['Ret_1M'],
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
    
    # 🎯 輸出矩陣：完美對齊大神最新面板
    headers_col = ["Ticker", "Industry", "Last Price", "1D%", "1M%", "1Y Trend", "1M Rank", "6M Rank", "1Y Rank", "操盤指令", "綜合評分", "應持有股數", "更新時間"]
    
    matrix = [[f"Momentum Portfolio V111 (Multi-TF RS)", f"{update_time}", ""] + [""] * 10, headers_col]
    
    for i, r in enumerate(top_10):
        # 標記高分發熱 (模擬熱力圖)
        r6m_str = f"{int(r['R6M'])} 🔥" if r['R6M'] >= 90 else f"{int(r['R6M'])}"
        r1y_str = f"{int(r['R1Y'])} 🔥" if r['R1Y'] >= 90 else f"{int(r['R1Y'])}"
        r1m_str = f"{int(r['R1M'])} ❄️" if r['R1M'] <= 30 else f"{int(r['R1M'])}"

        matrix.append([
            f"👑 {r['Ticker']}" if i < 3 else r['Ticker'], r['Industry'], 
            f"{round(r['Price'], 2)}", f"{r['1D']:+.2f}%", f"{r['1M']:+.2f}%", r['Trend'], 
            r1m_str, r6m_str, r1y_str, 
            r['Action'], f"{round(r['Score'], 1)}", r['TargetShares'], update_time
        ])

    print("📤 推送 V111 動能矩陣至 Google Sheets...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200: print("✅ V111 數據推送成功！")
    else: print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_super_growth_hk_v111()
