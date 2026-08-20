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
# 1. 系統配置中心 (V114 終極動量形態版 - 直白買賣提示)
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1fIw-8zcKpj8ALoSYszw8dG9SXsps63nXHnwRDOT2vWoXP6hf58t4XIkWnWvN4iUj/exec"
TARGET_SHEET = "HKv7-Share Screener"

PORTFOLIO_CAPITAL = 1_000_000  
TARGET_POSITIONS = 10
AVAILABLE_CAPITAL = PORTFOLIO_CAPITAL * 0.95 
TARGET_VALUE_PER_STOCK = AVAILABLE_CAPITAL / TARGET_POSITIONS 
BENCHMARK_INDEX = "^HSI" 

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
    return 100 - (100 / (1 + rs))

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
                'revenueGrowth': info.get('revenueGrowth', 0)
            }
        except: time.sleep(0.5)
    return t, {}

# ==========================================
# 3. 核心量化模型 V114 (直白行動版)
# ==========================================
def run_super_growth_hk_v114_explicit():
    update_time = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
    universe = list(set(GURU_LIST_HK))
    
    print("\n" + "="*60)
    print(f"🚀 [港股 動量矩陣 V114] 終極版啟動 | 直白買賣提示 (RPS領導股 + 形態狙擊點)")

    print("⏳ 掃描量價、大盤(HSI)與籌碼形態(VWAP)...")
    hist_all = yf.download(universe + [BENCHMARK_INDEX], period="2y", progress=False, threads=False)
    close_df, vol_df = hist_all['Close'], hist_all['Volume']
    high_df, low_df = hist_all['High'], hist_all['Low']
    
    hsi_close = close_df[BENCHMARK_INDEX].dropna() if BENCHMARK_INDEX in close_df else None
    
    tech_pool = {}
    for t in universe:
        if t not in close_df.columns or t not in vol_df.columns: continue
        c, v, h, l = close_df[t].dropna(), vol_df[t].dropna(), high_df[t].dropna(), low_df[t].dropna()
        if len(c) < 130: continue 
        
        p = float(c.iloc[-1])
        m50 = float(c.tail(50).mean())
        avg_vol_10 = float(v.tail(10).mean())
        if p < 1.0 or (avg_vol_10 * p) < 10_000_000 or p < m50: continue 

        ret_1m = get_ret(c, 21) * 100
        ret_3m = get_ret(c, 63) * 100
        ret_6m = get_ret(c, 126) * 100

        red_line_h20 = float(h.shift(1).tail(20).max())
        black_line_h60 = float(h.shift(1).tail(60).max())
        typical_price = (h + l + c) / 3
        vwap_20 = float((typical_price * v).tail(20).sum() / v.tail(20).sum())
        
        dist_vwap = ((p - vwap_20) / vwap_20) * 100
        dist_red = ((p - red_line_h20) / red_line_h20) * 100
        dist_black = ((p - black_line_h60) / black_line_h60) * 100
        vr = float(v.iloc[-1]) / float(v.tail(50).mean()) if float(v.tail(50).mean()) > 0 else 1.0

        rsi_14 = float(calculate_rsi(c, 14).iloc[-1])
        rs_trend_ok = False
        if hsi_close is not None:
            aligned_c, aligned_hsi = c.align(hsi_close, join='inner')
            rs_line = aligned_c / aligned_hsi
            rs_ma50 = rs_line.rolling(window=50).mean()
            if len(rs_line) > 50:
                rs_trend_ok = (rs_line.iloc[-1] > rs_ma50.iloc[-1]) and (rs_ma50.iloc[-1] > rs_ma50.iloc[-10])

        tech_pool[t] = {
            "P": p, "VR": vr, "RSI_14": rsi_14, "RS_Trend_OK": rs_trend_ok,
            "VWAP20": vwap_20, "DistVWAP": dist_vwap, "DistRed": dist_red, "DistBlack": dist_black,
            "Ret_1M": ret_1m, "Ret_3M": ret_3m, "Ret_6M": ret_6m,
            "Spark": ",".join([str(round(val, 2)) for val in c.tail(126).tolist()])
        }

    if not tech_pool: return print("⚠️ 查無符合標的。")

    rank_1m = (pd.Series({t: d['Ret_1M'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()
    rank_3m = (pd.Series({t: d['Ret_3M'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()
    rank_6m = (pd.Series({t: d['Ret_6M'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()

    for t in tech_pool:
        tech_pool[t]['20R'] = rank_1m.get(t, 0)
        tech_pool[t]['60R'] = rank_3m.get(t, 0)
        tech_pool[t]['120R'] = rank_6m.get(t, 0)
        tech_pool[t]['Total_Rank'] = (0.2 * tech_pool[t]['20R']) + (0.4 * tech_pool[t]['60R']) + (0.4 * tech_pool[t]['120R'])

    # 🛑 戰略過濾：嚴格要求 RPS 總分 >= 75，只做市場領導股
    filtered_tech_pool = {t: d for t, d in tech_pool.items() if d['Total_Rank'] >= 75}

    print(f"⏳ 拉取基本面 (過濾出 {len(filtered_tech_pool)} 檔市場領導股)...")
    infos = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        for t, info in executor.map(fetch_info_hk, list(filtered_tech_pool.keys())):
            if info: infos[t] = info

    all_cands = []
    for t, data in filtered_tech_pool.items():
        info = infos.get(t, {})
        sec, ind = info.get('sector'), info.get('industry')
        
        roe = (info.get('returnOnEquity') or 0) * 100
        rev_growth = (info.get('revenueGrowth') or 0) * 100
        fund_bonus = (10 if roe > 15 else 0) + (10 if rev_growth > 20 else 0)

        total_rank = data['Total_Rank']
        rsi = data['RSI_14']
        dist_vwap, dist_red, dist_black, vr = data['DistVWAP'], data['DistRed'], data['DistBlack'], data['VR']
        
        strategy_score = total_rank + fund_bonus
        
        # =======================================================
        # 🎯 終極戰術分析：直白顯示【買/賣/觀望】
        # =======================================================
        rs_tag = "📈跑贏大盤" if data['RS_Trend_OK'] else "⚠️大盤偏弱"
        
        action_tag = ""
        # 1. 賣出訊號：跌破主力防線
        if dist_vwap < -3.0: 
            action_tag = f"☠️【賣出】破主力線(VWAP{dist_vwap:+.1f}%)"
            strategy_score -= 20
        # 2. 買入訊號：大戰略突破
        elif dist_black > 0 and vr > 1.2:
            action_tag = "🟢【買入】大底放量突破"
            strategy_score += 15
        # 3. 買入訊號：短線突破
        elif dist_red > 0 and vr > 1.2:
            action_tag = "🟢【買入】短線放量突破"
            strategy_score += 10
        # 4. 買入訊號：完美回踩 (最佳買點)
        elif 0 <= dist_vwap <= 4.0 and vr < 0.8 and rsi < 60:
            action_tag = "🟢【強力買入】完美量縮回踩VWAP"
            strategy_score += 20 
        # 5. 止盈/觀望訊號：過熱警報
        elif dist_vwap > 8.0 or rsi > 70: 
            action_tag = f"💰【止盈/觀望】高位過熱(RSI:{rsi:.0f})"
            strategy_score -= 15
        # 6. 持股續抱訊號：沒有方向
        else:
            action_tag = f"🛡️【持股/觀望】均線震盪(RSI:{rsi:.0f})"

        # 結合 RS 狀態與個股戰術
        final_action = f"{rs_tag} | {action_tag}"
        # =======================================================
        
        price = data['P']
        stop_loss = price * 0.92 
        target_shares = max(100, round((TARGET_VALUE_PER_STOCK / price) / 100) * 100)

        all_cands.append({
            "Ticker": t, "Sector": sec, "Industry": ind[:10], 
            "Score": strategy_score, "Action": final_action, 
            "Price": price, "StopLoss": stop_loss,
            "TotalRank": total_rank, "R20": data['20R'], "R60": data['60R'], "R120": data['120R'],
            "TargetShares": target_shares,
            "Trend": f'=SPARKLINE({{{data["Spark"]}}}, {{"charttype","line";"color","black"}})'
        })

    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_10, sec_cnt = [], {}
    for r in all_cands:
        s = r['Sector']
        if sec_cnt.get(s, 0) >= 3: continue 
        top_10.append(r)
        sec_cnt[s] = sec_cnt.get(s, 0) + 1
        if len(top_10) >= TARGET_POSITIONS: break
    
    headers_col = ["Ticker", "Industry", "Last Price", "半年走勢", "RPS領導排名", "動量結構(20/60/120)", "直白買賣點 (大盤 | 行動指令)", "鐵血止損價", "綜合評分", "建議股數", "更新時間"]
    matrix = [[f"Momentum Portfolio V114 (戰略領導股 + 直白買賣提示版)", f"{update_time}", ""] + [""] * 8, headers_col]
    
    for i, r in enumerate(top_10):
        rank_str = f"{r['TotalRank']:.1f} 🔥" if r['TotalRank'] >= 80 else f"{r['TotalRank']:.1f}"
        struct_str = f"{int(r['R20'])} / {int(r['R60'])} / {int(r['R120'])}"

        matrix.append([
            f"👑 {r['Ticker']}" if i < 3 else r['Ticker'], r['Industry'], 
            f"{round(r['Price'], 2)}", r['Trend'], 
            rank_str, struct_str, r['Action'], 
            f"${round(r['StopLoss'], 2)}",
            f"{round(r['Score'], 1)}", r['TargetShares'], update_time
        ])

    print("📤 推送 V114 (直白買賣版) 矩陣至 Google Sheets...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200: 
        print(f"✅ V114 數據推送成功！Google 回傳: {response.text}")
    else: 
        print(f"❌ 推送失敗，狀態碼: {response.status_code}, 錯誤訊息: {response.text}")

if __name__ == "__main__":
    run_super_growth_hk_v114_explicit()
