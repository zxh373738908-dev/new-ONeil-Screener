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

# 🎯 載入富途 OpenAPI
try:
    from futu import *
    FUTU_AVAILABLE = True
except ImportError:
    FUTU_AVAILABLE = False
    print("⚠️ 未偵測到 futu-api，請確認是否已安裝 (pip install futu-api)。")

# ==========================================
# 1. 系統配置中心 (V115 Futu期權大單透視版)
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
# 🎯 Futu 期權大單透視引擎 (Put/Call Ratio)
# ==========================================
def check_futu_options(ctx, yf_ticker):
    if not ctx:
        return "-", 0
    try:
        time.sleep(0.5) # 防止觸發 API 頻率限制
        # 將 Yahoo 代碼轉換為 富途代碼 (0700.HK -> HK.00700)
        code = yf_ticker.split('.')[0].zfill(5)
        futu_code = f"HK.{code}"
        
        # 1. 獲取該股票的期權到期日列表
        ret, date_data = ctx.get_option_expiration_date(code=futu_code)
        if ret != RET_OK or date_data.empty:
            return "無期權", 0
            
        # 2. 選擇最近的一個到期日 (通常流動性最好)
        nearest_date = date_data['strike_time'][0]
        
        # 3. 獲取該到期日的完整期權鏈 (Option Chain)
        ret, chain = ctx.get_option_chain(code=futu_code, start=nearest_date, end=nearest_date)
        if ret != RET_OK or chain.empty:
            return "無期權數據", 0
            
        # 4. 篩選出 Call 和 Put 合約代碼
        calls = chain[chain['option_type'] == 'CALL']['code'].tolist()
        puts = chain[chain['option_type'] == 'PUT']['code'].tolist()
        
        # 為了避免 API 報錯，只取最活絡的 10 個 Call 和 10 個 Put 進行快照
        target_codes = calls[:10] + puts[:10]
        if not target_codes:
            return "合約無效", 0
            
        # 5. 抓取市場快照 (獲取今日累積成交量 Volume)
        ret, snapshots = ctx.get_market_snapshot(target_codes)
        if ret == RET_OK and not snapshots.empty:
            call_vols = snapshots[snapshots['code'].isin(calls)]['volume'].sum()
            put_vols = snapshots[snapshots['code'].isin(puts)]['volume'].sum()
            
            if call_vols + put_vols == 0:
                return "期權零成交", 0
                
            if put_vols == 0: put_vols = 1 # 避免除以零錯誤
            
            # 計算 PCR (Put/Call Ratio 的反向，看多比例)
            call_ratio = call_vols / put_vols
            
            if call_ratio > 2.5:
                return f"🔥大單暴買(C/P {call_ratio:.1f})", 25 # 極度看多
            elif call_ratio > 1.5:
                return f"📈多單偏多(C/P {call_ratio:.1f})", 15 # 溫和看多
            elif call_ratio < 0.5:
                return f"🚨空單湧入(C/P {call_ratio:.1f})", -25 # 極度看空 (主力買Put避險)
            else:
                return f"⚖️多空平衡(C/P {call_ratio:.1f})", 0
                
        return "快照失敗", 0
    except Exception as e:
        return f"API異常", 0

# ==========================================
# 3. 核心量化模型 V115
# ==========================================
def run_super_growth_hk_v115():
    update_time = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
    universe = list(set(GURU_LIST_HK))
    print("\n" + "="*60)
    print(f"🚀 [港股 動量矩陣 V115] 啟動 | Futu API 期權大單透視版")

    # 🎯 啟動 FutuOpenD 連線
    futu_ctx = None
    if FUTU_AVAILABLE:
        try:
            futu_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
            print("🟢 成功連接 FutuOpenD！正在開啟期權天眼...")
        except Exception as e:
            print("🔴 FutuOpenD 連接失敗！將以無期權數據模式繼續運行。")

    print("⏳ 掃描個股多維度報酬率與精確買點...")
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
        if p < m50: continue 

        red_line_h20 = float(h.shift(1).tail(20).max())
        black_line_h60 = float(h.shift(1).tail(60).max())
        typical_price = (h + l + c) / 3
        vwap_20 = float((typical_price * v).tail(20).sum() / v.tail(20).sum())
        
        dist_vwap = ((p - vwap_20) / vwap_20) * 100
        dist_red = ((p - red_line_h20) / red_line_h20) * 100
        dist_black = ((p - black_line_h60) / black_line_h60) * 100

        vr = float(v.iloc[-1]) / float(v.tail(50).mean()) if float(v.tail(50).mean()) > 0 else 1.0
        ret_1m, ret_6m, ret_1y = get_ret(c, 21)*100, get_ret(c, 126)*100, get_ret(c, 252)*100

        tech_pool[t] = {
            "P": p, "VR": vr, 
            "VWAP": vwap_20, "RedLine": red_line_h20, "BlackLine": black_line_h60, 
            "DistVWAP": dist_vwap, "DistRed": dist_red, "DistBlack": dist_black,
            "Ret_1M": ret_1m, "Ret_6M": ret_6m, "Ret_1Y": ret_1y,
            "Spark": ",".join([str(round(val, 2)) for val in c.tail(126).tolist()]) 
        }

    if not tech_pool: 
        print("⚠️ 查無符合標的。")
        if futu_ctx: futu_ctx.close()
        return

    rank_1m = (pd.Series({t: d['Ret_1M'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()
    rank_6m = (pd.Series({t: d['Ret_6M'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()
    rank_1y = (pd.Series({t: d['Ret_1Y'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()

    filtered_tech_pool = {t: d for t, d in tech_pool.items() if rank_6m.get(t, 0) >= 60 or rank_1y.get(t, 0) >= 60}

    print(f"⏳ 拉取基本面並交由 Futu OpenAPI 分析期權大單 (共 {len(filtered_tech_pool)} 檔)...")
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
        
        # 🎯 呼叫富途 API 分析該股票的期權大單
        option_msg, option_bonus = check_futu_options(futu_ctx, t)
        tech_score += option_bonus # 將聰明錢流向計入總分！
        
        if dist_vwap < -3.0: 
            action = f"✂️破線(VWAP {dist_vwap:+.1f}%)"
            tech_score *= 0.3 
        elif dist_black > 0 and vr > 1.2:
            action = f"🚀黑線突破(+量)"
            tech_score += 25 
        elif dist_red > 0 and vr > 1.2:
            action = f"🔥紅線突破(+量)"
            tech_score += 20 
        elif 0 <= dist_vwap <= 3.0 and vr < 0.8:
            action = f"🎯先勝回踩(量縮)"
            tech_score += 25 
        elif dist_vwap > 8.0: 
            action = f"👀過熱(VWAP {dist_vwap:+.1f}%)" 
        else: 
            action = f"🛡️均線震盪(等方向)"

        total_score = fund_score + tech_score
        
        price = data['P']
        raw_shares = TARGET_VALUE_PER_STOCK / price
        target_shares = max(100, round(raw_shares / 100) * 100)

        all_cands.append({
            "Ticker": t, "Industry": ind[:10], "Score": total_score, "Action": action, 
            "Price": price, "DistVWAP": dist_vwap, "DistRed": dist_red,
            "VWAP_Price": data['VWAP'], "RedLine_Price": data['RedLine'],
            "R1M": round(r1m, 0), "R6M": round(r6m, 0), "R1Y": round(r1y, 0),
            "TargetShares": target_shares, "OptionMsg": option_msg,
            "Trend": f'=SPARKLINE({{{data["Spark"]}}}, {{"charttype","line";"color","black"}})'
        })

    # 關閉富途 API 連線
    if futu_ctx:
        futu_ctx.close()
        print("🔴 FutuOpenD 連線已安全關閉。")

    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_10, sec_cnt = [], {}
    for r in all_cands:
        s = r['Sector']
        if sec_cnt.get(s, 0) >= 4: continue 
        top_10.append(r)
        sec_cnt[s] = sec_cnt.get(s, 0) + 1
        if len(top_10) >= TARGET_POSITIONS: break
    
    headers_col = ["Ticker", "Industry", "現價", "6M Rank", "1Y Rank", "🚀突破警報價(紅線)", "🎯埋伏低吸價(VWAP)", "操盤指令", "🔮期權大單透視", "綜合評分", "應持有股數", "更新時間"]
    
    matrix = [[f"Momentum Portfolio V115 (Futu OpenAPI 聰明錢透視)", f"{update_time}", ""] + [""] * 9, headers_col]
    
    for i, r in enumerate(top_10):
        r6m_str = f"{int(r['R6M'])} 🔥" if r['R6M'] >= 90 else f"{int(r['R6M'])}"
        r1y_str = f"{int(r['R1Y'])} 🔥" if r['R1Y'] >= 90 else f"{int(r['R1Y'])}"

        alert_price = f"HK${round(r['RedLine_Price'], 2)}" if r['DistRed'] < 0 else f"✅ 已突破!"
        buy_limit_price = f"HK${round(r['VWAP_Price'], 2)} (乖 {r['DistVWAP']:+.1f}%)" 

        matrix.append([
            f"👑 {r['Ticker']}" if i < 3 else r['Ticker'], r['Industry'], 
            f"HK${round(r['Price'], 2)}", 
            r6m_str, r1y_str, 
            alert_price, buy_limit_price, 
            r['Action'], r['OptionMsg'], f"{round(r['Score'], 1)}", r['TargetShares'], update_time
        ])

    print("📤 推送 V115 數據至 Google Sheets...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200: print("✅ V115 數據推送成功！")
    else: print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_super_growth_hk_v115()
