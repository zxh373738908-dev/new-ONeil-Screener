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
        time.sleep(random.uniform(0.04, 0.08))
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
        print(f"\n📡 正在傳送 {len(matrix)} 行先勝數據至 Google 試算表 [{sheet_name}]...")
        payload = {"sheet_name": sheet_name, "data": json.loads(json.dumps(matrix, default=str))}
        res = requests.post(WEBAPP_URL, json=payload, timeout=60)
        print(f"📥 伺服器狀態碼: {res.status_code}")
        if res.status_code == 200:
            print(f"🎉 恭喜！V105 真·先勝後戰決策版 已成功同步至 [{sheet_name}]！")
    except Exception as e: 
        print(f"❌ 同步失敗: {e}")

# =====================================================================
# 3. 核心量化模型 V105 (True Sun Tzu Decision Engine)
# =====================================================================
def run_true_sun_tzu_v105():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = get_universe()
    if "QQQ" not in universe: universe.append("QQQ")
    
    print("\n" + "="*60)
    print(f"⚔️ [真·先勝後戰量化系統 V105] 啟動 | 股票池總數: {len(universe)}")

    # 1. 批量下載數據
    hist_all = yf.download(universe, period="2y", progress=False, threads=True)
    close_df, vol_df, high_df, low_df = hist_all['Close'], hist_all['Volume'], hist_all['High'], hist_all['Low']
    qqq_c = close_df["QQQ"].dropna() if "QQQ" in close_df.columns else yf.Ticker("QQQ").history(period="2y")['Close']

    # 2. 多週期收益率與 RPS 排名
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

    # 3. 技術面與微觀結構分析
    stock_analysis = {}
    for t in valid_tickers:
        try:
            c, v, h, l = close_df[t].dropna(), vol_df[t].dropna(), high_df[t].dropna(), low_df[t].dropna()
            if len(c) < 130 or len(v) < 60: continue
            
            p, p_prev = float(c.iloc[-1]), float(c.iloc[-2])
            ema20 = float(c.ewm(span=20, adjust=False).mean().iloc[-1])
            
            # (A) RPS 多週期加權評分
            r20, r60, r120 = r20_rank.get(t, 50), r60_rank.get(t, 50), r120_rank.get(t, 50)
            total_rank = round((0.2 * r20) + (0.4 * r60) + (0.4 * r120), 1)

            # (B) RS/QQQ 動量線
            common_idx = c.index.intersection(qqq_c.index)
            rs_line = c.loc[common_idx] / qqq_c.loc[common_idx]
            rs_ma50 = rs_line.rolling(50).mean()
            rs_above_ma = bool(rs_line.iloc[-1] > rs_ma50.iloc[-1]) if len(rs_ma50.dropna()) > 0 else False
            rs_ma_up = bool(rs_ma50.iloc[-1] > rs_ma50.iloc[-5]) if len(rs_ma50.dropna()) >= 5 else False
            rs_strong = rs_above_ma and rs_ma_up

            # (C) VWMA(20) 機構籌碼線
            cv = c * v
            vwma20 = (cv.rolling(20).sum() / v.rolling(20).sum()).iloc[-1]
            vwma60 = (cv.rolling(60).sum() / v.rolling(60).sum()).iloc[-1]
            p_above_vwma = p > vwma20 and p > vwma60

            # (D) 微觀突破與 VCP 收斂
            black_line = float(c.tail(60).max())
            is_breakout = p >= black_line * 0.985
            tightness = float((c.tail(15).std() / c.tail(15).mean()) * 100)
            is_vcp = tightness < 3.2

            # (E) RSI 與 乖離率
            rsi_val = float(calculate_rsi(c, 14).iloc[-1])
            dist_to_ema20 = ((p - ema20) / ema20) * 100  # 修正為正規乖離率 (正代表在均線上方)
            vol_ratio = float(v.iloc[-1] / v.tail(20).mean()) if len(v) >= 20 else 1.0
            adr = float(((h - l) / l).tail(20).mean() * 100) if len(l) >= 20 else 2.0
            ytd = float((p / c.loc[c.index <= YTD_BASE_DATE].iloc[-1]) - 1) if not c.loc[c.index <= YTD_BASE_DATE].empty else 0.0

            # 市值備援估算 (若 API 未回傳)
            est_mcap = (p * v.tail(20).mean() * 50) / 1e9 

            spark_data = ",".join([str(round(val, 2)) for val in c.tail(60).tolist()])
            spark_formula = f'=SPARKLINE({{{spark_data}}}, {{"charttype","line";"linewidth",2;"color","blue"}})'

            stock_analysis[t] = {
                "Price": p, "1D": (p/p_prev) - 1, "Trend": spark_formula,
                "20R": r20, "60R": r60, "120R": r120, "TotalRank": total_rank,
                "RSI": rsi_val, "RS_Strong": rs_strong, "VWMA_Up": p_above_vwma,
                "Dist20": dist_to_ema20, "IsBreakout": is_breakout,
                "IsVCP": is_vcp, "Tight": tightness, "VolRatio": vol_ratio,
                "ADR": adr, "YTD": ytd, "EstMCap": est_mcap
            }
        except Exception:
            continue

    # 4. 基本面
    infos = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        for t, info in executor.map(fetch_info, list(stock_analysis.keys())):
            if info: infos[t] = info

    # 5. 真正的「先勝後戰」決策邏輯 (修正優先級)
    candidates = []
    for t, data in stock_analysis.items():
        if t not in infos: continue
        info = infos[t]
        ind = str(info.get('industry') or 'Unknown')
        sec = str(info.get('sector') or 'Unknown')
        
        mcap_val = info.get('marketCap')
        mcap = (float(mcap_val) / 1e9) if (mcap_val and float(mcap_val) > 0) else data['EstMCap']

        is_master = t in MASTER_CURRENT
        if not is_master and any(ex.lower() in ind.lower() for ex in EXCLUDED): continue

        tr = data['TotalRank']
        rsi = data['RSI']
        dist = data['Dist20']
        dist_fmt = f"{dist:+.1f}%"

        # 標籤
        tags = []
        if data['IsBreakout']: tags.append("🚀真空突破")
        if data['VWMA_Up']: tags.append("📈籌碼多頭")
        if data['RS_Strong']: tags.append("🔥RS強")
        if data['IsVCP']: tags.append("🎯VCP收斂")
        if data['VolRatio'] > 1.3: tags.append("爆量")
        
        if rsi >= 75: tags.append("⚠️極度過熱")
        elif 42 <= rsi <= 62: tags.append("黃金買區")
        elif rsi < 35: tags.append("超賣底背離")
        msg_str = "|".join(tags) if tags else "穩健"

        # ⚔️ 嚴格的先勝作戰指令（優先級：風控 > 禁追 > 先勝狙擊 > 觀察 > 淘汰）
        if is_master:
            if dist < -8.0:
                action = f"🛡️破止損線({dist_fmt})"
            elif tr < 70:
                action = f"⚠️動量衰竭({dist_fmt})"
            elif -2.5 <= dist <= 1.5 and 42 <= rsi <= 62:
                action = f"🎯安全加倉({dist_fmt})"
            elif rsi >= 75:
                action = f"👀過熱持倉({dist_fmt})"
            else:
                action = f"👑標準持倉({dist_fmt})"
        else:
            # 1. 淘汰弱勢
            if tr < 75 or not data['RS_Strong']:
                action = f"⚠️淘汰弱勢({dist_fmt})"
            # 2. 嚴禁追高（即使突破，RSI > 72 或 乖離 > 4.5% 也絕不給狙擊指令！）
            elif rsi >= 72 or dist > 4.5:
                action = f"👀過熱禁追({dist_fmt})"
            # 3. 🎯 真·先勝狙擊點（只在盈虧比極佳的黃金回踩或低位 VCP 突破時開火）
            elif tr >= 80 and data['RS_Strong']:
                if (-2.0 <= dist <= 3.0 and 42 <= rsi <= 65) and (data['IsVCP'] or data['IsBreakout'] or data['VWMA_Up']):
                    action = f"🎯先勝狙擊({dist_fmt})"
                else:
                    action = f"🔍列入觀察({dist_fmt})"
            else:
                action = f"🔍蓄勢待發({dist_fmt})"

        # 評分系統
        final_score = tr
        if data['RS_Strong']: final_score += 4
        if data['VWMA_Up']: final_score += 3
        if data['IsVCP']: final_score += 3
        if 42 <= rsi <= 62 and -2.0 <= dist <= 2.5: final_score += 5  # 打擊區暴擊加分
        if rsi >= 75: final_score -= 8  # 過熱重罰扣分
        if dist < -8.0: final_score *= 0.5
        if is_master: final_score += 1000

        candidates.append({
            "Ticker": t, "Name": str(info.get('shortName') or info.get('longName') or t)[:16],
            "Industry": ind, "Sector": sec, "MCap": mcap, "Price": data['Price'],
            "1D": data['1D'], "Trend": data['Trend'], "20R": data['20R'], "60R": data['60R'],
            "120R": data['120R'], "TotalRank": tr, "RSI": round(rsi, 1), "Action": action,
            "Msg": msg_str, "ADR": data['ADR'], "Vol": data['VolRatio'], "YTD": data['YTD'],
            "Score": final_score, "RS_Status": "🔥向上" if data['RS_Strong'] else "平緩"
        })

    candidates.sort(key=lambda x: x['Score'], reverse=True)

    # 挑選前 30 檔
    top_leaders, sec_count = [], {}
    for r in candidates:
        is_master = r['Ticker'] in MASTER_CURRENT
        if not is_master:
            if sec_count.get(r['Sector'], 0) >= 5: continue
            sec_count[r['Sector']] = sec_count.get(r['Sector'], 0) + 1
        top_leaders.append(r)
        if len(top_leaders) >= 30: break

    # 6. 組裝輸出矩陣
    headers = [
        "排名", "代碼", "名稱/行業", "作戰指令(真先勝)", "Msg結構標籤", 
        "Total Rank", "20R(1M)", "60R(3M)", "120R(6M)", "RSI(14)", 
        "RS/QQQ動量", "60日走勢(圖)", "現價", "1D%", "今年YTD", 
        "市值(Bil)", "量比", "ADR%", "風控倉位", "硬止損價(-8%)", "綜合評分", "更新時間"
    ]

    title_info = f"⚔️ 真·先勝後戰決策系統 V105 | 嚴禁 RSI>72 追高 | 嚴守 -8% 止損 | 鎖定 Top 20% 動量領導股"
    matrix = [[f"True Sun Tzu Momentum Master V105", f"更新: {update_time}", title_info] + [""] * (len(headers) - 3), headers]

    for i, r in enumerate(top_leaders):
        t_disp = f"👑 {r['Ticker']}" if r['Ticker'] in MASTER_CURRENT else r['Ticker']
        pos_limit = "12.5%" if r['TotalRank'] >= 80 else "8.0%"
        stop_loss_price = f_price(r['Price'] * 0.92)
        disp_score = f"{round(r['Score'] - 1000, 1)}" if r['Ticker'] in MASTER_CURRENT else f"{round(r['Score'], 1)}"

        matrix.append([
            f"T{i+1}", t_disp, f"{r['Ticker']} | {r['Industry'][:10]}", r['Action'], r['Msg'],
            f"{r['TotalRank']}分", f"{r['20R']}", f"{r['60R']}", f"{r['120R']}", f"{r['RSI']}",
            r['RS_Status'], r['Trend'], f_price(r['Price']), f_1d(r['1D']), f_pct(r['YTD']),
            f"${round(r['MCap'], 1)}B", f"{round(r['Vol'], 2)}x", f"{round(r['ADR'], 2)}%",
            pos_limit, f"{stop_loss_price}", disp_score, update_time
        ])

    sync_to_google_sheet(TARGET_SHEET, matrix)

if __name__ == "__main__":
    run_true_sun_tzu_v105()
