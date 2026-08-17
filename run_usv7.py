import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import requests
import json
import warnings
import time
import random
from concurrent.futures import ThreadPoolExecutor

warnings.filterwarnings('ignore')

# =====================================================================
# 1. 系統配置中心
# =====================================================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycbxtNb3Wb6gsabX3B0rYf3Ws_xnRetjqEum3j2sfFjW-PdttgTNdV0qC1gK3Jkicme6_/exec"
TARGET_SHEET = "us Screener"
YTD_BASE_DATE = "2025-12-31"

MASTER_CURRENT = ["AMD", "ARW", "ATI", "FTNT", "HPE", "HST", "STT", "VIK", "VSAT"]
SECTOR_LEADERS = ["FTI", "TDW", "PTEN", "VAL", "LBRT", "RIG", "NE", "BKR", "OIH", "XLE", "MU", "AMAT", "KLAC", "LRCX", "ADI", "DELL", "NTAP", "STX", "VLO"]

def get_universe():
    core_watchlist = list(set(MASTER_CURRENT + SECTOR_LEADERS + [
        "JBHT", "PRM", "ROIV", "ROKU", "TRGP", "YOU", "DAL", "GEV", "IBKR", 
        "LLY", "MNST", "RDDT", "PWR", "IRDM", "QS", "VRT", "FSLR", "SNDK", "NVDA", "QQQ"
    ]))
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', headers=headers, timeout=15)
        sp500 = pd.read_html(res.text)[0]['Symbol'].tolist()
        clean_sp500 = [t.replace('.', '-') for t in sp500]
        return list(set(clean_sp500 + core_watchlist))
    except:
        return core_watchlist

EXCLUDED = ['Commercial Banks', 'Savings Institutions', 'Mortgage', 'Real Estate']

# =====================================================================
# 2. 輔助計算函數
# =====================================================================
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50)

def get_ret(series, days):
    if series is None or len(series) < days + 1: return np.nan
    return (series.iloc[-1] / series.iloc[-(days + 1)]) - 1

def f_pct(v): return f"{round(v*100, 2)}%" if not pd.isna(v) else "0.00%"
def f_price(v): return f"${round(v, 2)}" if not pd.isna(v) else "$0.00"
def f_1d(v): return f"{v*100:+.2f}%" if not pd.isna(v) else "+0.00%"

def fetch_info(t):
    ticker = yf.Ticker(t)
    try:
        time.sleep(random.uniform(0.04, 0.10))
        info = ticker.info
        if info and 'industry' in info:
            info['industry'] = str(info['industry']).strip().replace('\t', '')
            return t, info
    except: pass
    try:
        fast = ticker.fast_info
        mcap = getattr(fast, 'market_cap', 0) or 0
        return t, {'industry': 'Growth/Tech', 'sector': 'Technology', 'marketCap': mcap, 'revenueGrowth': 0.15}
    except: return t, {}

def sync_to_google_sheet(sheet_name, matrix):
    try:
        print(f"\n📡 正在傳送 {len(matrix)} 行數據至 Google 試算表 [{sheet_name}]...")
        payload = {"sheet_name": sheet_name, "data": json.loads(json.dumps(matrix, default=str))}
        res = requests.post(WEBAPP_URL, json=payload, timeout=60)
        print(f"📥 伺服器狀態碼: {res.status_code}")
        print(f"📥 伺服器回應: {res.text}")
        if res.status_code == 200:
            print(f"🎉 恭喜！V104 先勝狙擊旗艦版 已成功同步至 [{sheet_name}]！")
    except Exception as e: 
        print(f"❌ 同步失敗: {e}")

# =====================================================================
# 3. 核心量化模型 V104 (Sun Tzu Momentum Master)
# =====================================================================
def run_sun_tzu_sniper_v104():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = get_universe()
    if "QQQ" not in universe: universe.append("QQQ")
    
    print("\n" + "="*60)
    print(f"⚔️ [先勝狙擊量化系統 V104] 啟動 | 股票池: {len(universe)}")
    print("🧠 正在運算：多週期 RPS Rank + RS/QQQ 動量線 + VWMA/CYC 雙線籌碼 + VCP 收斂...")

    # 1. 宏觀與歷史數據獲取
    hist_all = yf.download(universe, period="2y", progress=False, threads=True)
    close_df, vol_df, high_df, low_df = hist_all['Close'], hist_all['Volume'], hist_all['High'], hist_all['Low']

    qqq_c = close_df["QQQ"].dropna() if "QQQ" in close_df.columns else yf.Ticker("QQQ").history(period="2y")['Close']

    # 2. 全市場多週期動量收益率計算
    ret_20, ret_60, ret_120 = {}, {}, {}
    for t in universe:
        if t not in close_df.columns or t == "QQQ": continue
        c = close_df[t].dropna()
        if len(c) < 130: continue
        ret_20[t] = get_ret(c, 20)
        ret_60[t] = get_ret(c, 60)
        ret_120[t] = get_ret(c, 120)

    s_20, s_60, s_120 = pd.Series(ret_20).dropna(), pd.Series(ret_60).dropna(), pd.Series(ret_120).dropna()
    valid_tickers = list(set(s_20.index) & set(s_60.index) & set(s_120.index))
    
    r20_rank = (s_20.loc[valid_tickers].rank(pct=True) * 100).round(1).to_dict()
    r60_rank = (s_60.loc[valid_tickers].rank(pct=True) * 100).round(1).to_dict()
    r120_rank = (s_120.loc[valid_tickers].rank(pct=True) * 100).round(1).to_dict()

    # 3. 個股技術面與微觀結構計算
    stock_analysis = {}
    for t in valid_tickers:
        try:
            c, v, h, l = close_df[t].dropna(), vol_df[t].dropna(), high_df[t].dropna(), low_df[t].dropna()
            if len(c) < 130 or len(v) < 60: continue
            
            p, p_prev = float(c.iloc[-1]), float(c.iloc[-2])
            m20, m50, m200 = float(c.tail(20).mean()), float(c.tail(50).mean()), float(c.tail(200).mean()) if len(c)>=200 else float(c.tail(50).mean())
            ema20 = float(c.ewm(span=20, adjust=False).mean().iloc[-1])
            
            # (A) RPS 多週期加權評分 (0.2*20R + 0.4*60R + 0.4*120R)
            r20, r60, r120 = r20_rank.get(t, 50), r60_rank.get(t, 50), r120_rank.get(t, 50)
            total_rank = round((0.2 * r20) + (0.4 * r60) + (0.4 * r120), 1)

            # (B) RS/QQQ 動量線
            common_idx = c.index.intersection(qqq_c.index)
            rs_line = c.loc[common_idx] / qqq_c.loc[common_idx]
            rs_ma50 = rs_line.rolling(50).mean()
            rs_above_ma = bool(rs_line.iloc[-1] > rs_ma50.iloc[-1]) if len(rs_ma50.dropna()) > 0 else False
            rs_ma_up = bool(rs_ma50.iloc[-1] > rs_ma50.iloc[-5]) if len(rs_ma50.dropna()) >= 5 else False
            rs_strong = rs_above_ma and rs_ma_up

            # (C) VWMA(20) 與 CYC平替(VWMA60) 機構籌碼線
            cv = c * v
            vwma20 = (cv.rolling(20).sum() / v.rolling(20).sum()).iloc[-1]
            vwma60 = (cv.rolling(60).sum() / v.rolling(60).sum()).iloc[-1]
            p_above_vwma = p > vwma20 and p > vwma60

            # (D) 微觀結構：真空區、10日紅線、VCP波動收斂
            red_line = float(c.iloc[-11:-1].max())
            black_line = float(c.tail(60).max())
            is_breakout = p >= black_line * 0.985
            is_red_break = (p > red_line) and (p_prev <= red_line) and (p > vwma20)
            tightness = float((c.tail(15).std() / c.tail(15).mean()) * 100)
            is_vcp = tightness < 3.2  # 波動極致收斂

            # (E) RSI 與 打擊區乖離
            rsi_val = float(calculate_rsi(c, 14).iloc[-1])
            dist_to_ema20 = ((ema20 - p) / p) * 100
            vol_ratio = float(v.iloc[-1] / v.tail(20).mean()) if len(v) >= 20 else 1.0
            adr = float(((h - l) / l).tail(20).mean() * 100) if len(l) >= 20 else 2.0
            ytd = float((p / c.loc[c.index <= YTD_BASE_DATE].iloc[-1]) - 1) if not c.loc[c.index <= YTD_BASE_DATE].empty else 0.0

            spark_data = ",".join([str(round(val, 2)) for val in c.tail(60).tolist()])
            spark_formula = f'=SPARKLINE({{{spark_data}}}, {{"charttype","line";"linewidth",2;"color","blue"}})'

            stock_analysis[t] = {
                "Price": p, "1D": (p/p_prev) - 1, "Trend": spark_formula,
                "20R": r20, "60R": r60, "120R": r120, "TotalRank": total_rank,
                "RSI": rsi_val, "RS_Strong": rs_strong, "VWMA_Up": p_above_vwma,
                "Dist20": dist_to_ema20, "IsBreakout": is_breakout, "IsRedBreak": is_red_break,
                "IsVCP": is_vcp, "Tight": tightness, "VolRatio": vol_ratio,
                "ADR": adr, "YTD": ytd, "H60": black_line
            }
        except Exception:
            continue

    # 4. 抓取基本面
    infos = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        for t, info in executor.map(fetch_info, list(stock_analysis.keys())):
            if info: infos[t] = info

    # 5. 「先勝後戰」決策矩陣與評分
    candidates = []
    for t, data in stock_analysis.items():
        if t not in infos: continue
        info = infos[t]
        ind = str(info.get('industry') or 'Unknown')
        sec = str(info.get('sector') or 'Unknown')
        mcap_val = info.get('marketCap')
        mcap = (float(mcap_val) / 1e9) if mcap_val is not None else 0.0

        is_master = t in MASTER_CURRENT
        if not is_master and any(ex.lower() in ind.lower() for ex in EXCLUDED): continue

        tr = data['TotalRank']
        rsi = data['RSI']
        dist = data['Dist20']
        dist_fmt = f"{int(round(dist))}%"
        
        # 結構標籤
        tags = []
        if data['IsBreakout']: tags.append("🚀真空突破")
        elif data['IsRedBreak']: tags.append("⚡紅線突破")
        elif data['VWMA_Up']: tags.append("📈籌碼多頭")
        
        if data['RS_Strong']: tags.append("🔥RS強")
        if data['IsVCP']: tags.append("🎯VCP收斂")
        if data['VolRatio'] > 1.3: tags.append("爆量")
        
        if rsi < 35: tags.append("極度超賣")
        elif 40 <= rsi <= 62: tags.append("黃金買區")
        elif rsi > 75: tags.append("過熱")
        msg_str = "|".join(tags) if tags else "穩健"

        # 作戰指令 (先勝邏輯)
        if is_master:
            if dist < -8.0: action = f"🛡️破止損線({dist_fmt})"
            elif -3.0 <= dist <= 1.5: action = f"🎯加倉點({dist_fmt})"
            else: action = f"👑持倉中({dist_fmt})"
        else:
            if tr < 75:
                action = f"⚠️淘汰弱勢({dist_fmt})"
            elif tr >= 80 and data['RS_Strong']:
                # 滿足先勝條件：高動量 + RS向上 + (打擊區回踩 或 突破確認)
                if (-3.0 <= dist <= 2.5 and 40 <= rsi <= 65) or data['IsBreakout'] or data['IsVCP']:
                    action = f"🎯先勝狙擊({dist_fmt})"
                elif rsi > 75:
                    action = f"👀過熱禁追({dist_fmt})"
                else:
                    action = f"🔍列入觀察({dist_fmt})"
            elif tr >= 75:
                action = f"🔍蓄勢待發({dist_fmt})"
            else:
                action = f"👀觀望({dist_fmt})"

        # 評分系統：大格局動量佔 70% + 微觀籌碼突破佔 30%
        final_score = tr
        if data['RS_Strong']: final_score += 4
        if data['VWMA_Up']: final_score += 3
        if data['IsBreakout'] or data['IsRedBreak']: final_score += 4
        if data['IsVCP']: final_score += 3
        if 40 <= rsi <= 62: final_score += 3
        if dist < -8.0: final_score *= 0.5  # 破止損線重罰
        if is_master: final_score += 1000

        candidates.append({
            "Ticker": t, "Name": str(info.get('shortName') or info.get('longName') or t)[:18],
            "Industry": ind, "Sector": sec, "MCap": mcap, "Price": data['Price'],
            "1D": data['1D'], "Trend": data['Trend'], "20R": data['20R'], "60R": data['60R'],
            "120R": data['120R'], "TotalRank": tr, "RSI": round(rsi, 1), "Action": action,
            "Msg": msg_str, "ADR": data['ADR'], "Vol": data['VolRatio'], "YTD": data['YTD'],
            "Score": final_score, "RS_Status": "🔥向上" if data['RS_Strong'] else "平緩",
            "H60": data['H60']
        })

    candidates.sort(key=lambda x: x['Score'], reverse=True)

    # 挑選前 30 檔領導股（單一板塊最多 5 檔，維持分散）
    top_leaders, sec_count = [], {}
    for r in candidates:
        is_master = r['Ticker'] in MASTER_CURRENT
        if not is_master:
            if sec_count.get(r['Sector'], 0) >= 5: continue
            sec_count[r['Sector']] = sec_count.get(r['Sector'], 0) + 1
        top_leaders.append(r)
        if len(top_leaders) >= 30: break

    # 6. 組裝 Google Sheet 矩陣
    headers = [
        "排名", "代碼", "名稱/行業", "作戰指令(先勝)", "Msg結構標籤", 
        "Total Rank", "20R(1M)", "60R(3M)", "120R(6M)", "RSI(14)", 
        "RS/QQQ動量", "60日走勢(圖)", "現價", "1D%", "今年YTD", 
        "市值(Bil)", "量比", "ADR%", "風控倉位上限", "止損線設定(-8%)", "底層綜合評分", "更新時間"
    ]

    title_info = f"⚔️ 先勝狙擊旗艦版 V104 | 嚴守 -8% 無條件止損 | 倉位 ≤ 12.5% | Total Rank ≥ 80 鎖定頂級領先資產"
    matrix = [[f"Sun Tzu Momentum Master V104", f"更新: {update_time}", title_info] + [""] * (len(headers) - 3), headers]

    for i, r in enumerate(top_leaders):
        t_disp = f"👑 {r['Ticker']}" if r['Ticker'] in MASTER_CURRENT else r['Ticker']
        pos_limit = "12.5%" if r['TotalRank'] >= 80 else "8.0%"
        stop_loss_price = f_price(r['Price'] * 0.92)  # -8% 硬止損
        disp_score = round(r['Score'] - 1000, 1) if r['Ticker'] in MASTER_CURRENT else round(r['Score'], 1)

        matrix.append([
            f"T{i+1}", t_disp, f"{r['Ticker']} | {r['Industry'][:10]}", r['Action'], r['Msg'],
            f"{r['TotalRank']}分", f"{r['20R']}", f"{r['60R']}", f"{r['120R']}", f"{r['RSI']}",
            r['RS_Status'], r['Trend'], f_price(r['Price']), f_1d(r['1D']), f_pct(r['YTD']),
            f"${round(r['MCap'], 1)}B", f"{round(r['Vol'], 2)}x", f"{round(r['ADR'], 2)}%",
            pos_limit, f"{stop_loss_price}", disp_score, update_time
        ])

    sync_to_google_sheet(TARGET_SHEET, matrix)

if __name__ == "__main__":
    run_sun_tzu_sniper_v104()
