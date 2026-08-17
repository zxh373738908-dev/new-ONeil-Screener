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
# 1. 系統配置中心 (V113 市場領導股・動量矩陣版)
# ==========================================
# 更新為指定的 Web App URL
WEBAPP_URL = "https://script.google.com/macros/s/AKfycbwfstK4Xq1DXft4U3_Qg9pjCQ5Qp0FiIskzrKnT1VFdRiH5FFyk6Iikv0FAcZNrPtp-/exec"
# 更新為指定的 Google Sheet 分頁名稱
TARGET_SHEET = "HKv7-Share Screener"

PORTFOLIO_CAPITAL = 1_000_000  
TARGET_POSITIONS = 10
AVAILABLE_CAPITAL = PORTFOLIO_CAPITAL * 0.95 
TARGET_VALUE_PER_STOCK = AVAILABLE_CAPITAL / TARGET_POSITIONS 
BENCHMARK_INDEX = "^HSI" # 引入恆生指數作為計算 RS Line 的大盤基準

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

def calculate_rsi(series, period=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=period-1, adjust=False).mean()
    ema_down = down.ewm(com=period-1, adjust=False).mean()
    rs = ema_up / ema_down
    rsi = 100 - (100 / (1 + rs))
    return rsi

def fetch_info_hk(t):
    ticker = yf.Ticker(t)
    for i in range(2):
        try:
            time.sleep(random.uniform(0.1, 0.2))
            info = ticker.info
            return t, {
                'sector': str(info.get('sector', 'Unknown')),
                'industry': str(info.get('industry', 'Unknown')),
                'returnOnEquity': info.get('returnOnEquity', 0)
            }
        except: time.sleep(0.5)
    return t, {}

# ==========================================
# 3. 核心量化模型 V113 (融合 RPS 動量評級 + RS Line + RSI)
# ==========================================
def run_super_growth_hk_v113():
    update_time = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
    universe = list(set(GURU_LIST_HK))
    
    print("\n" + "="*60)
    print(f"🚀 [港股 動量矩陣 V113] 啟動 | 市場領導股策略 (RPS + RSI進場)")

    print("⏳ 掃描個股及大盤基準指數(HSI)多維度數據...")
    hist_all = yf.download(universe + [BENCHMARK_INDEX], period="2y", progress=False, threads=False)
    close_df, vol_df = hist_all['Close'], hist_all['Volume']
    high_df, low_df = hist_all['High'], hist_all['Low']
    
    # 獲取大盤數據用於計算 RS Line
    hsi_close = close_df[BENCHMARK_INDEX].dropna() if BENCHMARK_INDEX in close_df else None
    
    tech_pool = {}
    for t in universe:
        if t not in close_df.columns or t not in vol_df.columns: continue
        c, v, h, l = close_df[t].dropna(), vol_df[t].dropna(), high_df[t].dropna(), low_df[t].dropna()
        if len(c) < 130: continue # 至少需要半年的數據來計算 120R
        
        p = float(c.iloc[-1])
        m50 = float(c.tail(50).mean())
        avg_vol_10 = float(v.tail(10).mean())
        
        # 基礎流動性與防線過濾
        if p < 1.0 or (avg_vol_10 * p) < 10_000_000: continue 
        if p < m50: continue 

        # 🎯 1. 計算各週期的回報率 (對應文章中的 20R, 60R, 120R 週期)
        ret_1m = get_ret(c, 21) * 100   # 1個月約 21 個交易日
        ret_3m = get_ret(c, 63) * 100   # 3個月約 63 個交易日
        ret_6m = get_ret(c, 126) * 100  # 6個月約 126 個交易日

        # 🎯 2. 計算 RSI (用於輔助判斷進場點)
        rsi_14 = float(calculate_rsi(c, 14).iloc[-1])
        
        # 🎯 3. 計算相對強度線 RS Line (個股相對於大盤的強度)
        rs_trend_ok = False
        if hsi_close is not None:
            aligned_c, aligned_hsi = c.align(hsi_close, join='inner')
            rs_line = aligned_c / aligned_hsi
            rs_ma50 = rs_line.rolling(window=50).mean()
            if len(rs_line) > 50:
                # 文章條件：動量均線向上運行，且動量線高於均線
                is_above_ma = rs_line.iloc[-1] > rs_ma50.iloc[-1]
                is_ma_up = rs_ma50.iloc[-1] > rs_ma50.iloc[-10] 
                rs_trend_ok = is_above_ma and is_ma_up

        # 保留 VWAP 特徵作為回踩參考
        typical_price = (h + l + c) / 3
        vwap_20 = float((typical_price * v).tail(20).sum() / v.tail(20).sum())
        dist_vwap = ((p - vwap_20) / vwap_20) * 100

        tech_pool[t] = {
            "P": p, "DistVWAP": dist_vwap,
            "Ret_1M": ret_1m, "Ret_3M": ret_3m, "Ret_6M": ret_6m,
            "RSI_14": rsi_14, "RS_Trend_OK": rs_trend_ok,
            "Spark": ",".join([str(round(val, 2)) for val in c.tail(126).tolist()])
        }

    if not tech_pool: return print("⚠️ 查無符合標的。")

    # 🎯 4. 計算 RPS 動量強度排名 (百分位排名 0-100)
    rank_1m = (pd.Series({t: d['Ret_1M'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()
    rank_3m = (pd.Series({t: d['Ret_3M'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()
    rank_6m = (pd.Series({t: d['Ret_6M'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()

    for t in tech_pool:
        tech_pool[t]['20R'] = rank_1m.get(t, 0)
        tech_pool[t]['60R'] = rank_3m.get(t, 0)
        tech_pool[t]['120R'] = rank_6m.get(t, 0)
        # 文章公式: Total Rank = 0.2*20R + 0.4*60R + 0.4*120R (降低短期噪音權重)
        tech_pool[t]['Total_Rank'] = (0.2 * tech_pool[t]['20R']) + (0.4 * tech_pool[t]['60R']) + (0.4 * tech_pool[t]['120R'])

    # 🎯 5. 領導股嚴格篩選：Total Rank 至少 > 75 (文章建議優選 > 80)
    filtered_tech_pool = {t: d for t, d in tech_pool.items() if d['Total_Rank'] >= 75}

    print(f"⏳ 拉取基本面 (共過濾出 {len(filtered_tech_pool)} 檔高動量領導股)...")
    infos = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        for t, info in executor.map(fetch_info_hk, list(filtered_tech_pool.keys())):
            if info: infos[t] = info

    all_cands = []
    for t, data in filtered_tech_pool.items():
        info = infos.get(t, {})
        sec, ind = info.get('sector'), info.get('industry')
        
        total_rank = data['Total_Rank']
        rsi = data['RSI_14']
        rs_ok = data['RS_Trend_OK']
        
        # 基礎評分即為其 RPS 總動量分數
        strategy_score = total_rank 
        
        # 🎯 6. 制定進場點指令 (結合 RSI 與 RS Line)
        action_tags = []
        
        # RS Line 動態檢查
        if rs_ok:
            action_tags.append("📈跑贏大盤(RS向上)")
            strategy_score += 10
        else:
            action_tags.append("⚠️跑輸大盤(RS偏弱)")
            strategy_score -= 10
            
        # RSI 輔助擇時
        if rsi < 40:
            action_tags.append(f"🟢RSI低吸({rsi:.0f})")
            strategy_score += 15 # 高動量+低RSI = 最佳回調買點
        elif 40 <= rsi <= 65:
            action_tags.append(f"🟡RSI中性({rsi:.0f})")
            strategy_score += 5
        elif rsi > 70:
            action_tags.append(f"🔴RSI超買({rsi:.0f})")
            strategy_score -= 15 # 高動量+超買 = 容易短線見頂回調
            
        # 🎯 7. 風險控制：計算單筆頭寸 -8% 的嚴格止損價
        price = data['P']
        stop_loss_price = price * 0.92 
        
        raw_shares = TARGET_VALUE_PER_STOCK / price
        target_shares = max(100, round(raw_shares / 100) * 100)

        all_cands.append({
            "Ticker": t, "Sector": sec, "Industry": ind[:10], 
            "Score": strategy_score, "Action": " | ".join(action_tags), 
            "Price": price, "StopLoss": stop_loss_price,
            "TotalRank": total_rank, "R20": data['20R'], "R60": data['60R'], "R120": data['120R'],
            "TargetShares": target_shares,
            "Trend": f'=SPARKLINE({{{data["Spark"]}}}, {{"charttype","line";"color","black"}})'
        })

    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_10, sec_cnt = [], {}
    for r in all_cands:
        s = r['Sector']
        if sec_cnt.get(s, 0) >= 3: continue # 避免單一行業過於集中
        top_10.append(r)
        sec_cnt[s] = sec_cnt.get(s, 0) + 1
        if len(top_10) >= TARGET_POSITIONS: break
    
    # 輸出矩陣：採用全新的分析維度
    headers_col = ["Ticker", "Industry", "Last Price", "半年走勢圖", "RPS總排名(>80優)", "RPS結構(20/60/120)", "策略與進場點 (RSI)", "無條件止損價(-8%)", "綜合評分", "應持有股數", "更新時間"]
    
    matrix = [[f"Momentum Portfolio V113 (市場領導股策略)", f"{update_time}", ""] + [""] * 8, headers_col]
    
    for i, r in enumerate(top_10):
        # 凸顯高分領導股
        rank_str = f"{r['TotalRank']:.1f} 🔥" if r['TotalRank'] >= 80 else f"{r['TotalRank']:.1f}"
        struct_str = f"{int(r['R20'])} / {int(r['R60'])} / {int(r['R120'])}"

        matrix.append([
            f"👑 {r['Ticker']}" if i < 3 else r['Ticker'], r['Industry'], 
            f"{round(r['Price'], 2)}", r['Trend'], 
            rank_str, struct_str, r['Action'], 
            f"${round(r['StopLoss'], 2)}",
            f"{round(r['Score'], 1)}", r['TargetShares'], update_time
        ])

    print("📤 推送 V113 動量矩陣至 Google Sheets...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200: print("✅ V113 數據推送成功！")
    else: print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_super_growth_hk_v113()
