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
# 1. 系統配置中心 (港股專屬配置)
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"
TARGET_SHEET = "HK_Super"
YTD_BASE_DATE = "2023-12-31" # 調整為24年計算起點

# 港股核心資產池
GURU_LIST_HK = [
    "0700.HK", "9988.HK", "3690.HK", "1810.HK", "1211.HK", "2015.HK", "9868.HK", "9866.HK", 
    "0981.HK", "1347.HK", "0285.HK", "6618.HK", "9999.HK", "0883.HK", "0857.HK", "0386.HK",
    "0941.HK", "0762.HK", "0728.HK", "1088.HK", "1928.HK", "2020.HK", "6690.HK", "6862.HK",
    "2318.HK", "0388.HK", "1299.HK", "0005.HK", "0011.HK", "2382.HK", "0293.HK", "1024.HK",
    "0868.HK", "3800.HK", "2899.HK", "3993.HK", "0020.HK", "1929.HK", "6049.HK", "0772.HK",
    "1516.HK", "2269.HK", "2359.HK", "6608.HK", "9961.HK", "0268.HK", "0175.HK", "9618.HK",
    "9888.HK", "0992.HK", "1093.HK", "1177.HK", "2331.HK", "0322.HK", "0522.HK", "0836.HK",
    "0669.HK", "0151.HK", "6606.HK", "9992.HK", "9633.HK", "0867.HK", "0316.HK", "1997.HK"
]
EXCLUDED = ['Banks', 'Real Estate', 'REIT', 'Utilities']

def get_universe_hk():
    return list(set(GURU_LIST_HK))

# ==========================================
# 2. 輔助函數
# ==========================================
def fetch_info_hk(t):
    ticker = yf.Ticker(t)
    for i in range(2):
        try:
            time.sleep(random.uniform(0.1, 0.3))
            info = ticker.info
            if info and 'industry' in info:
                info['industry'] = str(info['industry']).strip().replace('\t', '')
                return t, info
        except: time.sleep(0.5)
    return t, {}

def get_ret(series, days):
    if series is None or len(series) < days + 1: return 0.0
    val = float(series.iloc[-(days+1)])
    if val == 0: return 0.0
    return (float(series.iloc[-1]) / val) - 1

# ==========================================
# 3. 核心量化模型 V73 Pro (Guru 級優化版)
# ==========================================
def run_super_growth_hk():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = get_universe_hk()
    print("\n" + "="*50)
    print(f"🚀 [港股超級成長股 V73 Pro Max] 啟動 | 載入恆指風控與VCP偵測...")

    # 1. 抓取大盤與宏觀引擎 (關閉 threads 避免 database locked)
    try:
        m_list = ["2800.HK", "CNH=X", "BNO"]
        m_data = yf.download(m_list, period="1y", progress=False, threads=False)['Close'].ffill()
        hsi = m_data['2800.HK'].dropna()
        cnh = m_data['CNH=X'].dropna()
        bno = m_data['BNO'].dropna()
        
        cnh_p = float(cnh.iloc[-1])
        cnh_trend = get_ret(cnh, 5) 
        bno_p = float(bno.iloc[-1])
        
        hsi_r = {20: get_ret(hsi, 20), 60: get_ret(hsi, 60), 120: get_ret(hsi, 120)}
        curr_hsi, ma20_hsi, ma50_hsi = float(hsi.iloc[-1]), float(hsi.tail(20).mean()), float(hsi.tail(50).mean())
        
        fx_alert = "🚨【匯率壓制】" if cnh_trend > 0.005 else ("💰【資金流入】" if cnh_trend < -0.005 else "平穩")
        macro_text = f"油:${bno_p:.1f}|USD/CNH:{cnh_p:.4f}|{fx_alert}"
    except Exception as e: 
        print(f"⚠️ 宏觀數據加載失敗: {e}")
        hsi_r, macro_text, curr_hsi, ma20_hsi, ma50_hsi, cnh_trend = {20:0, 60:0, 120:0}, "數據受限", 20.0, 20.0, 20.0, 0.0

    # 獨立抓取 VHSI 波幅指數，安全降級處理
    try:
        vhsi_df = yf.download("^VHSI", period="5d", progress=False, threads=False)['Close']
        if not vhsi_df.empty: vhsi = float(vhsi_df.dropna().iloc[-1])
        else: vhsi = 20.0
    except:
        vhsi = 20.0

    # 判定天氣
    if vhsi >= 28 or cnh_trend > 0.01: weather = "⛈️"
    elif curr_hsi > ma50_hsi and vhsi < 24: weather = "☀️"
    else: weather = "☁️"

    # 2. 技術掃描 (加入 VCP、量縮枯竭、ATR防守)
    print("⏳ 正在掃描港股技術面與量價結構...")
    hist_all = yf.download(universe, period="2y", progress=False, threads=False)
    
    if hist_all.empty:
        print("❌ 無法獲取股票歷史數據，請稍後再試。")
        return
        
    close_df, vol_df, high_df, low_df = hist_all['Close'], hist_all['Volume'], hist_all['High'], hist_all['Low']

    tech_pool, perfect_tickers, above_50ma, total_valid = {}, [], 0, 0
    for t in universe:
        try:
            if t not in close_df.columns: continue
            c, h, l, v = close_df[t].dropna(), high_df[t].dropna(), low_df[t].dropna(), vol_df[t].dropna()
            
            p = float(c.iloc[-1])
            # 基本過濾：剔除仙股與低流動性
            if len(c) < 150 or p < 1.0 or v.tail(10).mean() < 500000: continue
            
            m20, m50, m200 = float(c.tail(20).mean()), float(c.tail(50).mean()), float(c.tail(200).mean())
            
            total_valid += 1
            if p > m50: above_50ma += 1
            if p > m20 > m50 > m200: perfect_tickers.append(t)
            if p < m50: continue 
            
            risk = ((float(c.ewm(span=20, adjust=False).mean().iloc[-1]) - p) / p) * 100
            spark = ",".join([str(round(val, 2)) for val in c.tail(60).tolist()])
            
            try:
                base_price = float(c.asof(pd.Timestamp(YTD_BASE_DATE)))
                if pd.isna(base_price): base_price = float(c.iloc[0])
            except: base_price = float(c.iloc[0])
            ytd_val = (p / base_price) - 1

            # ==========================================
            # 🎯 Guru 級核心演算法 (ATR, VCP, VDU)
            # ==========================================
            # 1. 計算 14天 ATR (動態波動率)
            tr1 = h.tail(14) - l.tail(14)
            tr2 = abs(h.tail(14) - c.shift(1).tail(14))
            tr3 = abs(l.tail(14) - c.shift(1).tail(14))
            atr14 = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).mean()
            
            # 2. 偵測 VCP 價格收斂 (近15天最高與最低的震幅深度)
            recent_15_max = float(h.tail(15).max())
            recent_15_min = float(l.tail(15).min())
            consolidation_depth = (recent_15_max - recent_15_min) / recent_15_min
            
            # 3. 偵測 VDU 量縮枯竭 (Volume Dry-Up)
            vol_3d_avg = float(v.tail(3).mean())
            vol_50d_avg = float(v.tail(50).mean())
            is_vdu = vol_3d_avg < (vol_50d_avg * 0.6)
            
            # 4. 專業止損價位：收盤價向下 2倍 ATR，或 50MA (取較高者，嚴格防守)
            stop_loss_price = max(p - (2 * atr14), m50)

            tech_pool[t] = {
                "P": p, "1D": (p/float(c.iloc[-2]))-1, "Risk": risk,
                "VR": float(v.iloc[-1]) / vol_50d_avg if vol_50d_avg > 0 else 1.0, 
                "RS_Raw": (get_ret(c, 21)*0.4) + (get_ret(c, 63)*0.4) + (get_ret(c, 126)*0.2),
                "YTD": ytd_val,
                "ADR": float(((h - l) / l).tail(20).mean() * 100),
                "R20": get_ret(c, 20) - hsi_r.get(20, 0), "R60": get_ret(c, 60) - hsi_r.get(60, 0), "R120": get_ret(c, 120) - hsi_r.get(120, 0),
                "Spark": spark, "H60": float(h.tail(60).max()),
                "VCP_Depth": consolidation_depth * 100,
                "Is_VDU": is_vdu,
                "Stop_Loss": stop_loss_price
            }
        except Exception as e: continue

    if not tech_pool:
        print("❌ 沒有符合技術面條件的股票。")
        return

    # 3. 獲取基本面
    print("⏳ 正在拉取基本面與市值數據...")
    infos = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        for t, info in executor.map(fetch_info_hk, list(tech_pool.keys())):
            if info: infos[t] = info

    res_map = {}
    for t in perfect_tickers:
        ind = infos.get(t, {}).get('industry') or "Unknown"
        res_map[ind] = res_map.get(ind, 0) + 1

    # 4. 打分、排名與操作判定
    rs_ranks = (pd.Series({t: d['RS_Raw'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()
    all_cands = []
    
    for t, data in tech_pool.items():
        info, rs = infos.get(t, {}), rs_ranks.get(t, 0)
        
        # 🎯 放寬 RS 門檻至 75，避免漏掉剛起步的 VCP 黑馬
        if rs < 75: continue 
        sec, ind = str(info.get('sector', 'Unknown')), str(info.get('industry', 'Unknown'))
        if any(ex.lower() in ind.lower() for ex in EXCLUDED): continue
        
        # 🎯 Guru 邏輯：港股財報滯後，大幅降低財報權重，回歸價格動能
        rev_g = info.get('revenueGrowth', None)
        eps_g = info.get('earningsGrowth', None)
        
        fund_score = 0
        if rev_g is not None and rev_g > 0: fund_score += (rev_g * 100 * 0.1)
        if eps_g is not None and eps_g > 0: fund_score += (eps_g * 100 * 0.15)
        
        # 總分 = 80% 技術面強度 + 20% 財務面
        score = (rs * 0.80) + fund_score
            
        risk_v = round(data['Risk'], 1)
        vcp_d = data['VCP_Depth']
        
        # 🎯 Guru 邏輯：頂級買點判定 (量縮潛伏 vs 帶量突破)
        if data['Is_VDU'] and vcp_d < 12.0:
            action = "🤫量縮潛伏"
            score *= 1.25 # 給予極致收斂的股票加分
        elif data['P'] > data['H60'] * 0.98 and data['VR'] > 1.5:
            action = "🚀帶量突破"
            score *= 1.20
        elif -4.0 <= risk_v <= 2.0: 
            action = f"🎯均線狙擊"
        elif risk_v < -4.0: 
            action = f"⌛等回穩  "
        else: 
            action = f"📈乖離過大"

        # 止損距離計算 (%)
        sl_pct = ((data['Stop_Loss'] - data['P']) / data['P']) * 100
        msg = f"收斂:{round(vcp_d,1)}%|防守:{round(sl_pct,1)}%" 
        
        mkt_cap = info.get('marketCap', 0) / 1e9 
        
        all_cands.append({
            "Ticker": t, "Sector": sec, "Industry": ind[:16], "Score": score, "Action": action, "Msg": msg,
            "YTD": data['YTD'], "Trend": f'=SPARKLINE({{{data["Spark"]}}}, {{"charttype","line";"linewidth",2;"color","red"}})',
            "RS": rs, "Res": f"{res_map.get(ind, 0)}隻", "ADR": f"{round(data['ADR'], 2)}%", "Vol": f"{round(data['VR'], 2)}x",
            "Mkt": f"{round(mkt_cap, 1)}B ", "Price": f"HK${round(data['P'], 2)}", "1D": f"{data['1D']*100:+.2f}%",
            "R20": f"{round(data['R20']*100, 2)}%", "R60": f"{round(data['R60']*100, 2)}%", "R120": f"{round(data['R120']*100, 2)}%",
            "VP": f"HK${round(data['H60']*0.95, 1)}(突)" if data['P'] > data['H60']*0.95 else f"HK${round(data['H60'], 1)}(壓)",
            "StopLoss": f"HK${round(data['Stop_Loss'], 2)}"
        })

    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_15, s_cnt, i_cnt = [], {}, {}
    for r in all_cands:
        if s_cnt.get(r['Sector'], 0) >= 5 or i_cnt.get(r['Industry'], 0) >= 3: continue
        top_15.append(r)
        s_cnt[r['Sector']] = s_cnt.get(r['Sector'], 0) + 1
        i_cnt[r['Industry']] = i_cnt.get(r['Industry'], 0) + 1
        if len(top_15) >= 15: break

    # 5. 恆指對沖建議
    hedge_ticker = f"🛡️ 2800.HK Tracker Fund"
    hedge_action = "🚨 建議對沖  " if vhsi > 25.0 or curr_hsi < ma20_hsi else "💤 暫無風險  "
    hedge_row = [hedge_ticker, "大盤保險", "N/A", hedge_action, "VHSI 港股指引", "-", "-", "-", "-", "-", "-", "-", "-", "-", f"HK${round(curr_hsi, 2)}", "-", "-", "-", "✅ 保底", "-", update_time]

    # 6. 輸出至 Google Sheets (更新表頭)
    headers = ["Ticker", "Industry", "Score", "Action", "Guru指標(收斂/防守)", "From 2024 YTD", "60日趨勢(圖)", "REL20", "REL60", "REL120", "RS_Rank", "行業共振", "ADR", "量比", "價格", "1D%", "MktCap", "籌碼峰", "防守止損位", "大盤建議", "更新時間"]
    hk_breadth = (above_50ma / total_valid * 100) if total_valid > 0 else 0
    
    m_status = f"天气:{weather}|多頭排列:{len(perfect_tickers)}隻|港股池宽度:{hk_breadth:.1f}%|VHSI波幅:{round(vhsi,1)}|{macro_text}"
    row1 = [f"HK SuperGrowth V73 Pro Max", f"港股宏觀: {m_status}", ""] + [""] * 18
    
    matrix = [row1, headers]
    for i, r in enumerate(top_15):
        matrix.append([
            f"👑 {r['Ticker']}" if i < 3 else r['Ticker'], r['Industry'], f"{round(r['Score'], 1)} ", 
            r['Action'], r['Msg'], f"{round(r['YTD']*100, 2)}%", r['Trend'], 
            r['R20'], r['R60'], r['R120'], f"{round(r['RS'], 1)} ", r['Res'], 
            r['ADR'], r['Vol'], r['Price'], r['1D'], r['Mkt'], r['VP'], 
            r['StopLoss'], "✅ 持有", update_time
        ])
    matrix.append(hedge_row)

    print("📤 正在推送資料到 Google Sheets...")
    response = requests.post(WEBAPP_URL, json={"sheet_name": TARGET_SHEET, "data": matrix}, timeout=60)
    
    if response.status_code == 200:
        print("✅ 港股數據已成功推送至 Google Sheets！")
    else:
        print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_super_growth_hk()
