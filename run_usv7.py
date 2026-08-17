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
# 1. 系統配置中心 (已綁定您的專屬 Web App 與 工作表)
# =====================================================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycbxtNb3Wb6gsabX3B0rYf3Ws_xnRetjqEum3j2sfFjW-PdttgTNdV0qC1gK3Jkicme6_/exec"
TARGET_SHEET = "us Screener"
YTD_BASE_DATE = "2025-12-31"

# 核心自選與強勢板塊龍頭池
MASTER_CURRENT = ["AMD", "ARW", "ATI", "FTNT", "HPE", "HST", "STT", "VIK", "VSAT"]
SECTOR_LEADERS = ["FTI", "TDW", "PTEN", "VAL", "LBRT", "RIG", "NE", "BKR", "OIH", "XLE", "MU", "AMAT", "KLAC", "LRCX", "ADI"]

def get_universe():
    """獲取 S&P500 + 核心龍頭股票池"""
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
# 2. 輔助計算函數 (RPS, RSI, 動量線)
# =====================================================================
def calculate_rsi(series, period=14):
    """計算 RSI 指標"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)

def get_ret(series, days):
    """計算特定天數報酬率"""
    if series is None or len(series) < days + 1: return np.nan
    return (series.iloc[-1] / series.iloc[-(days + 1)]) - 1

def f_pct(v): return f"{round(v*100, 2)}%" if not pd.isna(v) else "0.00%"
def f_price(v): return f"${round(v, 2)}" if not pd.isna(v) else "$0.00"
def f_1d(v): return f"{v*100:+.2f}%" if not pd.isna(v) else "+0.00%"

def fetch_info(t):
    """抓取基本面數據與市值"""
    ticker = yf.Ticker(t)
    try:
        time.sleep(random.uniform(0.05, 0.12))
        info = ticker.info
        if info and 'industry' in info:
            info['industry'] = str(info['industry']).strip().replace('\t', '')
            return t, info
    except: pass
    try:
        fast = ticker.fast_info
        return t, {'industry': 'Technology/Energy', 'sector': 'Growth', 'marketCap': fast.market_cap, 'revenueGrowth': 0.15}
    except: return t, {}

def sync_to_google_sheet(sheet_name, matrix):
    """透過 Web App 同步至 Google Sheet"""
    try:
        print(f"\n📡 正在傳送 {len(matrix)} 行領導股數據至 [{sheet_name}]...")
        payload = {"sheet_name": sheet_name, "data": json.loads(json.dumps(matrix, default=str))}
        res = requests.post(WEBAPP_URL, json=payload, timeout=60)
        print(f"📥 伺服器狀態碼: {res.status_code}")
        print(f"📥 伺服器回應: {res.text}")
        if res.status_code == 200:
            print(f"🎉 恭喜！動量領導股清單已成功同步至 Google Sheet [{sheet_name}]！")
    except Exception as e: 
        print(f"❌ 同步失敗: {e}")

# =====================================================================
# 3. 核心量化模型 V103 (Top-Down Momentum Leaders)
# =====================================================================
def run_momentum_screener_v103():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = get_universe()
    if "QQQ" not in universe: universe.append("QQQ")
    
    print("\n" + "="*60)
    print(f"🚀 [動量領導股篩選模型 V103] 啟動 | 掃描標的數: {len(universe)}")
    print("📌 正在計算 20R / 60R / 120R RPS 排名、RS/QQQ 動量線與 RSI 擇時...")

    # 1. 批量下載 2 年歷史 K 線
    hist_all = yf.download(universe, period="2y", progress=False, threads=True)
    close_df = hist_all['Close']
    vol_df = hist_all['Volume']
    high_df = hist_all['High']
    low_df = hist_all['Low']

    if "QQQ" not in close_df.columns:
        print("⚠️ 無法獲取基準 QQQ 數據，嘗試單獨下載...")
        qqq_c = yf.Ticker("QQQ").history(period="2y")['Close']
    else:
        qqq_c = close_df["QQQ"].dropna()

    # 2. 計算全市場動量收益率 (20D, 60D, 120D)
    ret_20, ret_60, ret_120 = {}, {}, {}
    for t in universe:
        if t not in close_df.columns or t == "QQQ": continue
        c = close_df[t].dropna()
        if len(c) < 130: continue
        ret_20[t] = get_ret(c, 20)
        ret_60[t] = get_ret(c, 60)
        ret_120[t] = get_ret(c, 120)

    # 3. 計算 RPS 百分位排名 (0 ~ 100 分)
    s_20 = pd.Series(ret_20).dropna()
    s_60 = pd.Series(ret_60).dropna()
    s_120 = pd.Series(ret_120).dropna()

    valid_tickers = list(set(s_20.index) & set(s_60.index) & set(s_120.index))
    
    # 按照文章百分位排名公式計算
    r20_rank = (s_20.loc[valid_tickers].rank(pct=True) * 100).round(1).to_dict()
    r60_rank = (s_60.loc[valid_tickers].rank(pct=True) * 100).round(1).to_dict()
    r120_rank = (s_120.loc[valid_tickers].rank(pct=True) * 100).round(1).to_dict()

    # 4. 個股動量線、RSI、技術結構分析
    stock_analysis = {}
    for t in valid_tickers:
        try:
            c = close_df[t].dropna()
            v = vol_df[t].dropna()
            h = high_df[t].dropna()
            l = low_df[t].dropna()
            
            p = float(c.iloc[-1])
            p_prev = float(c.iloc[-2])
            m20 = float(c.tail(20).mean())
            m50 = float(c.tail(50).mean())
            m200 = float(c.tail(200).mean()) if len(c) >= 200 else m50
            ema20 = float(c.ewm(span=20, adjust=False).mean().iloc[-1])
            
            # 加權總評分 Total Rank: 0.2*20R + 0.4*60R + 0.4*120R
            r20 = r20_rank.get(t, 50)
            r60 = r60_rank.get(t, 50)
            r120 = r120_rank.get(t, 50)
            total_rank = round((0.2 * r20) + (0.4 * r60) + (0.4 * r120), 1)

            # RSI(14) 擇時指標
            rsi_series = calculate_rsi(c, 14)
            rsi_val = float(rsi_series.iloc[-1])

            # RS 動量線分析 (Stock / QQQ) 與 RS 50日均線
            common_idx = c.index.intersection(qqq_c.index)
            rs_line = c.loc[common_idx] / qqq_c.loc[common_idx]
            rs_ma50 = rs_line.rolling(50).mean()
            
            rs_above_ma = bool(rs_line.iloc[-1] > rs_ma50.iloc[-1]) if len(rs_ma50.dropna()) > 0 else False
            rs_ma_up = bool(rs_ma50.iloc[-1] > rs_ma50.iloc[-5]) if len(rs_ma50.dropna()) >= 5 else False
            rs_momentum_strong = rs_above_ma and rs_ma_up

            # 突破結構
            high_60 = float(c.tail(60).max())
            is_breakout = p >= high_60 * 0.985
            dist_to_ema20 = ((ema20 - p) / p) * 100

            # 迷你趨勢圖 Sparkline
            spark_data = ",".join([str(round(val, 2)) for val in c.tail(60).tolist()])
            spark_formula = f'=SPARKLINE({{{spark_data}}}, {{"charttype","line";"linewidth",2;"color","blue"}})'
            
            vol_ratio = float(v.iloc[-1] / v.tail(20).mean()) if len(v) >= 20 else 1.0
            adr = float(((h - l) / l).tail(20).mean() * 100) if len(l) >= 20 else 2.0
            ytd = float((p / c.loc[c.index <= YTD_BASE_DATE].iloc[-1]) - 1) if not c.loc[c.index <= YTD_BASE_DATE].empty else 0.0

            stock_analysis[t] = {
                "Price": p, "1D": (p/p_prev) - 1, "Trend": spark_formula,
                "20R": r20, "60R": r60, "120R": r120, "TotalRank": total_rank,
                "RSI": rsi_val, "RS_Strong": rs_momentum_strong,
                "Dist20": dist_to_ema20, "IsBreakout": is_breakout, "VolRatio": vol_ratio,
                "ADR": adr, "YTD": ytd, "P_gt_50MA": p > m50, "Perfect_Trend": p > m20 > m50 > m200
            }
        except Exception:
            continue

    print(f"✅ 完成 {len(stock_analysis)} 檔標的之動量評分！正在拉取基本面與板塊分類...")

    # 5. 獲取基本面 (產業與市值)
    infos = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        for t, info in executor.map(fetch_info, list(stock_analysis.keys())):
            if info: infos[t] = info

    # 6. 自上而下篩選與作戰指令生成
    candidates = []
    for t, data in stock_analysis.items():
        if t not in infos: continue
        info = infos[t]
        ind = str(info.get('industry', 'Unknown'))
        sec = str(info.get('sector', 'Unknown'))
        mcap = info.get('marketCap', 0) / 1e9  # 單位：十億美元 (Billion)
        
        is_master = t in MASTER_CURRENT
        if not is_master and any(ex.lower() in ind.lower() for ex in EXCLUDED): continue

        total_rank = data['TotalRank']
        rsi = data['RSI']
        dist = data['Dist20']
        dist_fmt = f"{int(round(dist))}%"
        
        # 標籤建構
        tags = []
        if data['IsBreakout']: tags.append("🚀突破")
        if data['RS_Strong']: tags.append("🔥RS強")
        if data['VolRatio'] > 1.3: tags.append("爆量")
        if rsi < 35: tags.append("極度超賣")
        elif 40 <= rsi <= 60: tags.append("回踩買區")
        elif rsi > 75: tags.append("過熱")
        msg_str = "|".join(tags) if tags else "穩健"

        # 作戰指令 (基於文章進入機制與風控)
        if is_master:
            if dist < -8.0: action = f"🛡️止損線({dist_fmt})"
            elif -3.0 <= dist <= 1.5: action = f"🎯加倉({dist_fmt})"
            else: action = f"👑持倉({dist_fmt})"
        else:
            if total_rank < 75:
                action = f"⚠️淘汰({dist_fmt})"
            elif total_rank >= 80 and data['RS_Strong']:
                if 40 <= rsi <= 62 or data['IsBreakout']:
                    action = f"🎯狙擊進場({dist_fmt})"
                elif rsi > 75:
                    action = f"👀過熱觀望({dist_fmt})"
                else:
                    action = f"🔍列入觀察({dist_fmt})"
            elif total_rank >= 75:
                action = f"🔍蓄勢中({dist_fmt})"
            else:
                action = f"👀觀望({dist_fmt})"

        # 綜合排序分數 (以 TotalRank 為核心，結合突破與 RS 強度)
        final_score = total_rank
        if data['RS_Strong']: final_score += 5
        if data['IsBreakout']: final_score += 5
        if 40 <= rsi <= 60: final_score += 3
        if is_master: final_score += 1000  # 確保自選龍頭優先列出

        candidates.append({
            "Ticker": t, "Name": info.get('shortName', t)[:18], "Industry": ind, "Sector": sec,
            "MCap": mcap, "Price": data['Price'], "1D": data['1D'], "Trend": data['Trend'],
            "20R": data['20R'], "60R": data['60R'], "120R": data['120R'], "TotalRank": total_rank,
            "RSI": round(rsi, 1), "Action": action, "Msg": msg_str, "ADR": data['ADR'],
            "Vol": data['VolRatio'], "YTD": data['YTD'], "Score": final_score,
            "RS_Status": "🔥向上" if data['RS_Strong'] else "平緩"
        })

    # 依綜合分數降序排列
    candidates.sort(key=lambda x: x['Score'], reverse=True)

    # 取前 35 檔領導股 (兼顧板塊分散度)
    top_leaders, sec_count = [], {}
    for r in candidates:
        is_master = r['Ticker'] in MASTER_CURRENT
        if not is_master:
            if sec_count.get(r['Sector'], 0) >= 6: continue
            sec_count[r['Sector']] = sec_count.get(r['Sector'], 0) + 1
        top_leaders.append(r)
        if len(top_leaders) >= 30: break

    # =====================================================================
    # 4. 組裝 Google Sheet 輸出矩陣
    # =====================================================================
    headers = [
        "排名", "代碼", "名稱/行業", "作戰指令", "Msg結構標籤", 
        "Total Rank", "20R(1M)", "60R(3M)", "120R(6M)", "RSI(14)", 
        "RS/QQQ動量", "60日走勢(圖)", "現價", "1D%", "今年YTD", 
        "市值(Bil)", "量比", "ADR%", "風控倉位上限", "止損線設定", "底層評分", "更新時間"
    ]

    title_info = f"🏆 動量領導股系統 V103 | 嚴守 -8% 無條件止損 | 倉位 ≤ 12.5% | Total Rank > 80 鎖定領先資產"
    matrix = [[f"Momentum Leaders Screener", f"更新: {update_time}", title_info] + [""] * (len(headers) - 3), headers]

    for i, r in enumerate(top_leaders):
        t_disp = f"👑 {r['Ticker']}" if r['Ticker'] in MASTER_CURRENT else r['Ticker']
        pos_limit = "12.5%" if r['TotalRank'] >= 80 else "8.0%"
        stop_loss_price = f_price(r['Price'] * 0.92)  # -8% 止損價
        disp_score = round(r['Score'] - 1000, 1) if r['Ticker'] in MASTER_CURRENT else round(r['Score'], 1)

        matrix.append([
            f"T{i+1}", t_disp, f"{r['Ticker']} | {r['Industry'][:10]}", r['Action'], r['Msg'],
            f"{r['TotalRank']}分", f"{r['20R']}", f"{r['60R']}", f"{r['120R']}", f"{r['RSI']}",
            r['RS_Status'], r['Trend'], f_price(r['Price']), f_1d(r['1D']), f_pct(r['YTD']),
            f"${round(r['MCap'], 1)}B", f"{round(r['Vol'], 2)}x", f"{round(r['ADR'], 2)}%",
            pos_limit, f"{stop_loss_price}(-8%)", disp_score, update_time
        ])

    sync_to_google_sheet(TARGET_SHEET, matrix)

if __name__ == "__main__":
    run_momentum_screener_v103()
