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
# 1. 系統配置中心 (A股 V114 終極先勝後戰版 - 自帶買賣點)
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycbw_f6Uy1OMIIl-4mLsAaxe1rXr64qYf2j0RHoKl3-xu0QOp-5kqFpk9rTBIV9Yf5-kz/exec"
TARGET_SHEET = "A-Share screener"  # 🎯 輸出至 A 股專屬表格

PORTFOLIO_CAPITAL = 1_000_000  
TARGET_POSITIONS = 10
AVAILABLE_CAPITAL = PORTFOLIO_CAPITAL * 0.95 
TARGET_VALUE_PER_STOCK = AVAILABLE_CAPITAL / TARGET_POSITIONS 
BENCHMARK_INDEX = "000300.SS" # 🇨🇳 使用滬深300作為大盤基準

# 🚀 A股強勢股票池
GURU_LIST_A = [
    "603986.SS", "301308.SZ", "688525.SS", "688041.SS", "688256.SS", "002049.SZ",
    "000938.SZ", "000977.SZ", "603019.SS", "300454.SZ", "300759.SZ", "002230.SZ",
    "601138.SS", "300308.SZ", "002475.SZ", "601127.SS", "600938.SS", "601816.SS", 
    "002352.SZ", "600754.SS", "603259.SS", "600276.SS", "601888.SS", "300750.SZ", 
    "002594.SZ", "600519.SS", "000858.SZ", "600036.SS", "601088.SS", "601857.SS"
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

def fetch_info_a(t):
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
# 3. 核心量化模型
# ==========================================
def run_super_growth_a_v114():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = list(set(GURU_LIST_A))
    
    print("\n" + "="*65)
    print(f"🚀 [A股 終極動量 V114] 啟動 | 自動計算具體買賣點")

    hist_all = yf.download(universe + [BENCHMARK_INDEX], period="2y", progress=False, threads=False)
    close_df, vol_df = hist_all['Close'], hist_all['Volume']
    high_df, low_df = hist_all['High'], hist_all['Low']
    
    bm_close = close_df[BENCHMARK_INDEX].dropna() if BENCHMARK_INDEX in close_df else None
    
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
        if bm_close is not None:
            aligned_c, aligned_bm = c.align(bm_close, join='inner')
            rs_line = aligned_c / aligned_bm
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

    # 🛑 戰略過濾：嚴格要求 RPS 總分 >= 75
    filtered_tech_pool = {t: d for t, d in tech_pool.items() if d['Total_Rank'] >= 75}

    infos = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        for t, info in executor.map(fetch_info_a, list(filtered_tech_pool.keys())):
            if info: infos[t] = info

    all_cands = []
    for t, data in filtered_tech_pool.items():
        info = infos.get(t, {})
        sec, ind = info.get('sector', 'Unknown'), info.get('industry', 'Unknown')
        
        roe = (info.get('returnOnEquity') or 0) * 100
        rev_growth = (info.get('revenueGrowth') or 0) * 100
        fund_bonus = (10 if roe > 10 else 0) + (10 if rev_growth > 15 else 0) 

        total_rank = data['Total_Rank']
        rsi = data['RSI_14']
        dist_vwap, dist_red, dist_black, vr = data['DistVWAP'], data['DistRed'], data['DistBlack'], data['VR']
        
        strategy_score = total_rank + fund_bonus
        
        rs_tag = "📈跑贏滬深300" if data['RS_Trend_OK'] else "⚠️大盤偏弱"
        
        action_tag = ""
        if dist_vwap < -3.0: 
            action_tag = f"✂️跌破籌碼線(VWAP{dist_vwap:+.1f}%)"
            strategy_score -= 20
        elif dist_black > 0 and vr > 1.2:
            action_tag = "🚀大底突破(放量)"
            strategy_score += 15
        elif dist_red > 0 and vr > 1.2:
            action_tag = "🔥短線突破(放量)"
            strategy_score += 10
        elif 0 <= dist_vwap <= 4.0 and vr < 0.8 and rsi < 60:
            action_tag = "🎯完美回踩VWAP(量縮低吸)"
            strategy_score += 20 
        elif dist_vwap > 8.0 or rsi > 70: 
            action_tag = f"🔴過熱勿追(RSI:{rsi:.0f}/VWAP{dist_vwap:+.1f}%)"
            strategy_score -= 15
        else:
            action_tag = f"🛡️均線震盪(RSI:{rsi:.0f})"

        final_action = f"{rs_tag} | {action_tag}"
        
        price = data['P']
        vwap = data['VWAP20']
        
        # 🔥 計算精確的買點與賣點
        ideal_buy_price = vwap  # 買點：20日均價成本線
        take_profit_price = vwap * 1.10  # 止盈賣點：向上偏離 10% (容易引發超買回調)
        stop_loss_price = price * 0.92  # 止損賣點：-8%
        
        target_shares = int(max(100, math.floor((TARGET_VALUE_PER_STOCK / price) / 100) * 100))

        all_cands.append({
            "Ticker": t, "Sector": sec, "Industry": ind[:12], 
            "Score": strategy_score, "Action": final_action, 
            "Price": price, "IdealBuy": ideal_buy_price, "TakeProfit": take_profit_price, "StopLoss": stop_loss_price,
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
    
    # 🌟 輸出矩陣設計：加入精確的 買點 與 賣點
    headers_col = ["代碼", "現價", "🎯 VWAP伏击(买点)", "🔴 超买警戒(止盈卖点)", "✂️ 铁血防线(止损卖点)", "戰術指令 (大盤狀態 | 籌碼與形態)", "RPS領導排名", "動量結構(20/60/120)", "半年走勢", "建議股數", "更新時間"]
    matrix = [[f"A-Share Momentum V114 (帶精確買賣點)", f"{update_time}", ""] + [""] * 8, headers_col]
    
    for i, r in enumerate(top_10):
        rank_str = f"{r['TotalRank']:.1f} 🔥" if r['TotalRank'] >= 80 else f"{r['TotalRank']:.1f}"
        struct_str = f"{int(r['R20'])} / {int(r['R60'])} / {int(r['R120'])}"

        matrix.append([
            f"👑 {r['Ticker']}" if i < 3 else r['Ticker'], 
            f"¥{round(r['Price'], 2)}", 
            f"¥{round(r['IdealBuy'], 2)}",      # 🎯 買點
            f"¥{round(r['TakeProfit'], 2)}",    # 🔴 止盈賣點
            f"¥{round(r['StopLoss'], 2)}",      # ✂️ 止損賣點
            r['Action'], rank_str, struct_str, 
            r['Trend'], 
            f"{r['TargetShares']:,} 股", # 確保格式為純文字
            update_time
        ])

    print(f"📤 推送 A股 V114 (買賣點版) 至 Google Sheets ({TARGET_SHEET})...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200: 
        print(f"✅ V114 數據推送成功！現在表格已顯示精確的『買點』與『賣點』。")
    else: 
        print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_super_growth_a_v114()
