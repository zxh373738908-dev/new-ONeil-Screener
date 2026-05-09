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
# 1. 系統配置中心 (A股專屬配置)
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"
TARGET_SHEET = "A_Super" # 請確保您的 Google Sheet 有建立此工作表
YTD_BASE_DATE = "2023-12-31"

# A股大神歷史經理重倉池 (茅指數、寧組合、頂級公募核心資產)
GURU_LIST_A =[
    # 滬市核心 (白酒/醫藥/金融/電力/半導體)
    "600519.SS", "600276.SS", "601318.SS", "600036.SS", "601166.SS", "601012.SS", "600900.SS", "603259.SS",
    "600030.SS", "600809.SS", "601888.SS", "600438.SS", "600031.SS", "601899.SS", "603288.SS", "601088.SS",
    "601225.SS", "600048.SS", "600690.SS", "601628.SS", "600584.SS", "600028.SS", "600309.SS", "600104.SS",
    "600745.SS", "603501.SS", "600111.SS", "601919.SS", "600887.SS", "603986.SS", "600406.SS", "601816.SS",
    # 深市核心 (新能源/家電/醫療/安防/消費)
    "300750.SZ", "000858.SZ", "002594.SZ", "000333.SZ", "000651.SZ", "002415.SZ", "300015.SZ", "300760.SZ",
    "002304.SZ", "002142.SZ", "002475.SZ", "002271.SZ", "002236.SZ", "000568.SZ", "002714.SZ", "002027.SZ",
    "002311.SZ", "300124.SZ", "300274.SZ", "300059.SZ", "000938.SZ", "300408.SZ", "002050.SZ", "002841.SZ",
    "000002.SZ", "000725.SZ", "002460.SZ", "000792.SZ", "000001.SZ", "300014.SZ", "300122.SZ", "300347.SZ"
]

EXCLUDED =['Banks', 'Real Estate', 'REIT', 'Utilities']

def get_universe_a():
    return list(set(GURU_LIST_A))

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
# 3. 核心量化模型 V73 Pro (A股 Guru 優化版)
# ==========================================
def run_super_growth_a():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = get_universe_a()
    print("\n" + "="*50)
    print(f"🚀 [A股超級成長股 V73 Pro Max] 啟動 | 載入滬深300風控與VCP偵測...")

    # 1. 抓取大盤與宏觀引擎 (000300.SS 為滬深300指數)
    try:
        m_list =["000300.SS", "CNY=X", "BNO"]
        m_data = yf.download(m_list, period="1y", progress=False, threads=False)['Close'].ffill()
        csi = m_data['000300.SS'].dropna()
        cny = m_data['CNY=X'].dropna()
        bno = m_data['BNO'].dropna()
        
        cny_p = float(cny.iloc[-1])
        cny_trend = get_ret(cny, 5) 
        bno_p = float(bno.iloc[-1])
        
        csi_r = {20: get_ret(csi, 20), 60: get_ret(csi, 60), 120: get_ret(csi, 120)}
        curr_csi, ma20_csi, ma50_csi = float(csi.iloc[-1]), float(csi.tail(20).mean()), float(csi.tail(50).mean())
        
        fx_alert = "🚨【外資流出】" if cny_trend > 0.005 else ("💰【外資流入】" if cny_trend < -0.005 else "平穩")
        macro_text = f"油:${bno_p:.1f}|USD/CNY:{cny_p:.4f}|{fx_alert}"
        
        # 計算滬深300的20日歷史年化波動率 (替代港股 VHSI)
        csi_ret = csi.pct_change().dropna()
        csi_vol = float(csi_ret.tail(20).std() * np.sqrt(252) * 100)
    except Exception as e: 
        print(f"⚠️ 宏觀數據加載失敗: {e}")
        csi_r, macro_text, curr_csi, ma20_csi, ma50_csi, cny_trend, csi_vol = {20:0, 60:0, 120:0}, "數據受限", 3000.0, 3000.0, 3000.0, 0.0, 20.0

    # 判定天氣 (A股波動率一般較低，大於25視為震盪加劇)
    if csi_vol >= 25 or cny_trend > 0.01: weather = "⛈️"
    elif curr_csi > ma50_csi and csi_vol < 20: weather = "☀️"
    else: weather = "☁️"

    # 2. 技術掃描 (加入 VCP、量縮枯竭、ATR防守)
    print("⏳ 正在掃描A股技術面與量價結構...")
    hist_all = yf.download(universe, period="2y", progress=False, threads=False)
    
    if hist_all.empty:
        print("❌ 無法獲取股票歷史數據，請稍後再試。")
        return
        
    close_df, vol_df, high_df, low_df = hist_all['Close'], hist_all['Volume'], hist_all['High'], hist_all['Low']

    tech_pool, perfect_tickers, above_50ma, total_valid = {},[], 0, 0
    for t in universe:
        try:
            if t not in close_df.columns: continue
            c, h, l, v = close_df[t].dropna(), high_df[t].dropna(), low_df[t].dropna(), vol_df[t].dropna()
            
            p = float(c.iloc[-1])
            # 基本過濾：剔除仙股與低流動性 (A股流動性較佳，提高過濾門檻)
            if len(c) < 150 or p < 1.0 or v.tail(10).mean() < 1000000: continue
            
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
            tr1 = h.tail(14) - l.tail(14)
            tr2 = abs(h.tail(14) - c.shift(1).tail(14))
            tr3 = abs(l.tail(14) - c.shift(1).tail(14))
            atr14 = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).mean()
            
            recent_15_max = float(h.tail(15).max())
            recent_15_min = float(l.tail(15).min())
            consolidation_depth = (recent_15_max - recent_15_min) / recent_15_min
            
            vol_3d_avg = float(v.tail(3).mean())
            vol_50d_avg = float(v.tail(50).mean())
            is_vdu = vol_3d_avg < (vol_50d_avg * 0.6)
            
            stop_loss_price = max(p - (2 * atr14), m50)

            tech_pool[t] = {
                "P": p, "1D": (p/float(c.iloc[-2]))-1, "Risk": risk,
                "VR": float(v.iloc[-1]) / vol_50d_avg if vol_50d_avg > 0 else 1.0, 
                "RS_Raw": (get_ret(c, 21)*0.4) + (get_ret(c, 63)*0.4) + (get_ret(c, 126)*0.2),
                "YTD": ytd_val,
                "ADR": float(((h - l) / l).tail(20).mean() * 100),
                "R20": get_ret(c, 20) - csi_r.get(20, 0), "R60": get_ret(c, 60) - csi_r.get(60, 0), "R120": get_ret(c, 120) - csi_r.get(120, 0),
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
        for t, info in executor.map(fetch_info_a, list(tech_pool.keys())):
            if info: infos[t] = info

    res_map = {}
    for t in perfect_tickers:
        ind = infos.get(t, {}).get('industry') or "Unknown"
        res_map[ind] = res_map.get(ind, 0) + 1

    # 4. 打分、排名與操作判定
    rs_ranks = (pd.Series({t: d['RS_Raw'] for t, d in tech_pool.items()}).rank(pct=True) * 100).to_dict()
    all_cands =[]
    
    for t, data in tech_pool.items():
        info, rs = infos.get(t, {}), rs_ranks.get(t, 0)
        
        if rs < 75: continue 
        sec, ind = str(info.get('sector', 'Unknown')), str(info.get('industry', 'Unknown'))
        if any(ex.lower() in ind.lower() for ex in EXCLUDED): continue
        
        rev_g = info.get('revenueGrowth', None)
        eps_g = info.get('earningsGrowth', None)
        
        fund_score = 0
        if rev_g is not None and rev_g > 0: fund_score += (rev_g * 100 * 0.1)
        if eps_g is not None and eps_g > 0: fund_score += (eps_g * 100 * 0.15)
        
        score = (rs * 0.80) + fund_score
            
        risk_v = round(data['Risk'], 1)
        vcp_d = data['VCP_Depth']
        
        if data['Is_VDU'] and vcp_d < 12.0:
            action = "🤫量縮潛伏"
            score *= 1.25 
        elif data['P'] > data['H60'] * 0.98 and data['VR'] > 1.5:
            action = "🚀帶量突破"
            score *= 1.20
        elif -4.0 <= risk_v <= 2.0: 
            action = f"🎯均線狙擊"
        elif risk_v < -4.0: 
            action = f"⌛等回穩  "
        else: 
            action = f"📈乖離過大"

        sl_pct = ((data['Stop_Loss'] - data['P']) / data['P']) * 100
        msg = f"收斂:{round(vcp_d,1)}%|防守:{round(sl_pct,1)}%" 
        
        mkt_cap = info.get('marketCap', 0) / 1e9 
        
        all_cands.append({
            "Ticker": t, "Sector": sec, "Industry": ind[:16], "Score": score, "Action": action, "Msg": msg,
            "YTD": data['YTD'], "Trend": f'=SPARKLINE({{{data["Spark"]}}}, {{"charttype","line";"linewidth",2;"color","red"}})',
            "RS": rs, "Res": f"{res_map.get(ind, 0)}隻", "ADR": f"{round(data['ADR'], 2)}%", "Vol": f"{round(data['VR'], 2)}x",
            "Mkt": f"¥{round(mkt_cap, 1)}B ", "Price": f"¥{round(data['P'], 2)}", "1D": f"{data['1D']*100:+.2f}%",
            "R20": f"{round(data['R20']*100, 2)}%", "R60": f"{round(data['R60']*100, 2)}%", "R120": f"{round(data['R120']*100, 2)}%",
            "VP": f"¥{round(data['H60']*0.95, 1)}(突)" if data['P'] > data['H60']*0.95 else f"¥{round(data['H60'], 1)}(壓)",
            "StopLoss": f"¥{round(data['Stop_Loss'], 2)}"
        })

    all_cands.sort(key=lambda x: x['Score'], reverse=True)
    top_15, s_cnt, i_cnt =[], {}, {}
    for r in all_cands:
        if s_cnt.get(r['Sector'], 0) >= 5 or i_cnt.get(r['Industry'], 0) >= 3: continue
        top_15.append(r)
        s_cnt[r['Sector']] = s_cnt.get(r['Sector'], 0) + 1
        i_cnt[r['Industry']] = i_cnt.get(r['Industry'], 0) + 1
        if len(top_15) >= 15: break

    # 5. 滬深300對沖建議 (用 510300.SS 華泰柏瑞滬深300ETF 作為防守工具)
    hedge_ticker = f"🛡️ 510300.SS (CSI 300 ETF)"
    hedge_action = "🚨 建議對沖  " if csi_vol > 25.0 or curr_csi < ma20_csi else "💤 暫無風險  "
    hedge_row =[hedge_ticker, "大盤保險", "N/A", hedge_action, "滬深300 波幅指引", "-", "-", "-", "-", "-", "-", "-", "-", "-", f"¥{round(curr_csi, 2)}", "-", "-", "-", "✅ 保底", "-", update_time]

    # 6. 輸出至 Google Sheets
    headers =["Ticker", "Industry", "Score", "Action", "Guru指標(收斂/防守)", "From 2024 YTD", "60日趨勢(圖)", "REL20", "REL60", "REL120", "RS_Rank", "行業共振", "ADR", "量比", "價格", "1D%", "MktCap", "籌碼峰", "防守止損位", "大盤建議", "更新時間"]
    a_breadth = (above_50ma / total_valid * 100) if total_valid > 0 else 0
    
    m_status = f"天气:{weather}|多頭排列:{len(perfect_tickers)}隻|A股池寬度:{a_breadth:.1f}%|CSI波幅:{round(csi_vol,1)}|{macro_text}"
    row1 =[f"A-Share SuperGrowth V73 Pro Max", f"A股宏觀: {m_status}", ""] + [""] * 18
    
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
        print("✅ A股數據已成功推送至 Google Sheets！")
    else:
        print(f"❌ 推送失敗，狀態碼: {response.status_code}")

if __name__ == "__main__":
    run_super_growth_a()
