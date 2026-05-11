import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import requests
import json
import warnings
import math
import concurrent.futures
import time

warnings.filterwarnings('ignore')

# ==========================================
# 1. A 股配置中心 (核心成長與龍頭)
# ==========================================
# 這裡填入你的 Google Apps Script 部署網址
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"

# A 股核心種子池 (白馬股 + 賽道龍頭)
A_CORE_TICKERS = [
    "600519", "601318", "000858", "600036", "600900", "000333", "601012", "300750", "300760", "600276",
    "601888", "002594", "002475", "603259", "002714", "601899", "603288", "600585", "600309", "002415"
]

# A 股擴充池 (包含各行業領先者)
FALLBACK_UNIVERSE = A_CORE_TICKERS + [
    "600104", "002352", "601166", "601398", "601288", "601939", "601988", "600030", "000001", "600000",
    "600887", "600690", "000651", "000725", "601668", "600019", "600048", "601327", "601601", "601628",
    "300059", "300413", "300015", "300124", "600438", "601088", "002142", "601919", "600941", "601728"
]

EXCLUDED_INDUSTRIES = ['Banks', 'Insurance', 'Real Estate']
MAX_PER_SECTOR = 3  

# ==========================================
# 2. 核心計算裝甲
# ==========================================
def sync_to_google_sheet(sheet_name, matrix):
    try:
        def safe_json_val(val):
            if isinstance(val, float) and not math.isfinite(val): return 0
            return str(val)
        payload = {"sheet_name": sheet_name, "data": json.loads(json.dumps(matrix, default=safe_json_val))}
        requests.post(WEBAPP_URL, json=payload, timeout=30)
        print(f"🎉 A股同步成功 -> [{sheet_name}]")
    except Exception as e: 
        print(f"❌ 同步失敗: {e}")

def safe_get(info_dict, key, default=0):
    val = info_dict.get(key)
    try: return float(val) if val is not None else default
    except: return default

def extract_ticker_data(data, ticker):
    try:
        if isinstance(data.columns, pd.MultiIndex):
            if ticker in data.columns.levels[0]: return data[ticker].dropna()
            elif ticker in data.columns.levels[1]: return data.xs(ticker, level=1, axis=1).dropna()
        return data.dropna()
    except: return pd.DataFrame()

def calculate_return(series, p):
    try:
        if len(series) > p: return (float(series.iloc[-1]) / float(series.iloc[-(p+1)]) - 1) * 100
    except: pass
    return 0

def format_a_tickers(ticker_list):
    """將純數字代碼轉為 Yahoo Finance 格式 (.SS 或 .SZ)"""
    formatted = []
    for t in ticker_list:
        t_str = str(t).strip().zfill(6)
        if t_str.startswith(('60', '68', '90')):
            formatted.append(f"{t_str}.SS")
        else:
            formatted.append(f"{t_str}.SZ")
    return list(set(formatted))

# ==========================================
# 3. 基本面併發獲取引擎 (針對 A 股優化)
# ==========================================
def fetch_fundamental_data(c):
    try:
        time.sleep(0.1)
        info = yf.Ticker(c['YF_T']).info
        sec = str(info.get('sector', 'Unknown'))
        
        if any(ex.lower() in sec.lower() for ex in EXCLUDED_INDUSTRIES): return None
        
        rev_g = safe_get(info, 'revenueGrowth') * 100
        op_m = safe_get(info, 'operatingMargins') * 100
        div_yield = safe_get(info, 'dividendYield') * 100
        is_tech = 'Technology' in sec or 'Electronics' in sec or 'Software' in str(info.get('industry', ''))
        
        # A 股特有的高增長 R40 或 高股息估值邏輯
        if is_tech:
            fin_score, msg_prefix = rev_g + op_m, "科技成長"
        elif div_yield > 3.5:
            fin_score, msg_prefix = op_m + div_yield * 2, f"高息價值({div_yield:.1f}%)"
        else:
            fin_score, msg_prefix = op_m + rev_g, "綜合優勢"
            
        if fin_score > 0 or c['RPS'] > 80:
            c['Sec'] = sec[:10].replace('Consumer C', 'Cons.C').replace('Consumer D', 'Cons.D')
            c['Fin_S'] = fin_score
            c['Msg'] = f"{msg_prefix}({fin_score:.0f}%)" + (" ✨" if c['Tight'] < 2.5 else "")
            
            dist = abs(c['P'] - c['EMA20']) / c['P'] * 100
            score = (c['RPS'] * 0.5) + (min(fin_score, 100) * 0.15)
            
            # 針對 A 股的技術面加分 (A股較常沿著 EMA20 噴發)
            if dist < 1.2: score += 40             
            if c['Bias'] > 12: score -= (c['Bias'] - 12) * 10 
            if c['Tight'] < 2.5: score += 20       
            if c['RVOL'] > 1.8: score += 10        
            
            c['Score'], c['Dist'] = score, dist
            return c
    except: pass
    return None

# ==========================================
# 4. 🚀 主引擎: A 股 V80.9 先勝後戰版
# ==========================================
def run_a_right_side_momentum():
    print("\n" + "="*50 + "\n🚀 [策略 A-Share: V80.9 極速版] 啟動...")
    
    try:
        # 使用上證指數作為市場情緒參考
        market_ref = yf.download("000001.SS", period="5d", progress=False)
        m_change = float((market_ref['Close'].iloc[-1] / market_ref['Close'].iloc[-2] - 1) * 100)
    except: 
        m_change = 0.0

    tickers = format_a_tickers(FALLBACK_UNIVERSE)
    print(f"📡 正在掃描 A 股 {len(tickers)} 隻龍頭部隊...")
    data = yf.download(tickers, period="2y", interval="1d", group_by='ticker', auto_adjust=True, progress=False)
    
    stats_list = []
    for t in tickers:
        df = extract_ticker_data(data, t)
        if df.empty or len(df) < 200: continue
        close, vol = df['Close'], df['Volume']
        
        # 過濾流動性極差的 A 股 (成交量過濾)
        if close.iloc[-1] < 2.0 or vol.tail(5).mean() < 500000: continue

        stats_list.append({
            "T": t.split('.')[0], "YF_T": t, "df": df, "close": close, "vol": vol,
            "r20": calculate_return(close, 20), "r60": calculate_return(close, 60),
            "r120": calculate_return(close, 120), "r250": calculate_return(close, 250)
        })
    
    if not stats_list:
        print("❌ 未抓取到有效數據。")
        return

    df_stats = pd.DataFrame(stats_list)
    for col, period in [('20R', 'r20'), ('60R', 'r60'), ('120R', 'r120')]:
        df_stats[col] = df_stats[period].rank(pct=True) * 100
        
    # A 股短期動能權重略高，因為 A 股趨勢較陡
    df_stats['RPS'] = (df_stats['20R'] * 0.4) + (df_stats['60R'] * 0.3) + (df_stats['120R'] * 0.3)

    raw_cands = []
    for _, row in df_stats.iterrows():
        df, close = row['df'], row['close']
        curr_p, ma50 = float(close.iloc[-1]), close.tail(50).mean()
        ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
        
        # 過濾：RPS 需大於 75 且 價格在 50 日線之上
        if row['RPS'] < 75 or curr_p < ma50: continue

        prices_str = ",".join([str(round(p, 2)) for p in close.tail(60).tolist()])
        sparkline_cmd = f'=SPARKLINE({{{prices_str}}}, {{"charttype","line";"color","#E74C3C"}})' # A股用紅色代表漲

        raw_cands.append({
            "T": row['T'], "YF_T": row['YF_T'], "P": curr_p, "RPS": row['RPS'], "EMA20": ema20,
            "1D": calculate_return(close, 1), "Bias": ((curr_p - ma50)/ma50)*100,
            "ADR": ((df['High']-df['Low'])/df['Low']).tail(20).mean()*100,
            "RVOL": float(row['vol'].iloc[-1] / max(row['vol'].tail(10).mean(), 1)),
            "Tight": float((close.tail(15).std() / close.tail(15).mean()) * 100),
            "Trend": sparkline_cmd
        })

    top_cands = sorted(raw_cands, key=lambda x: x['RPS'], reverse=True)[:60]
    print(f"🔬 啟動多線程基本面掃描 (共 {len(top_cands)} 隻)...")

    final_pool = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(fetch_fundamental_data, top_cands)
        for res in results:
            if res is not None: final_pool.append(res)

    sorted_final = sorted(final_pool, key=lambda x: x['Score'], reverse=True)
    top10, sector_counts, sector_map = [], {}, {}
    
    for r in sorted_final: sector_map[r['Sec']] = sector_map.get(r['Sec'], 0) + 1

    for r in sorted_final:
        if sector_counts.get(r['Sec'], 0) < MAX_PER_SECTOR:
            # 策略指令針對 A 股漲跌停特性調整
            if r['Bias'] > 15: action = "🚫 乖離過大(等回踩)"
            elif r['Score'] > 85 and r['Dist'] < 1.5: action = "⚡ 買入信號"
            elif r['Bias'] < 6: action = "🕯️ 縮量橫盤"
            else: action = f"觀察(距買點{r['Dist']:.1f}%)"
            
            t_display = ("🔥" if sector_map.get(r['Sec'], 0) >= 3 else "") + r['T']
            
            row_data = [
                f"N{len(top10)+1}",
                t_display,
                r['Sec'],
                round(r['P'], 2),
                f"{r['1D']:.1f}%",
                f"{r['ADR']:.1f}%",
                f"{r['Bias']:.1f}%",
                r['Trend'],
                f"{r['RPS']:.1f}",
                r['Msg'],
                f"{r['Score']:.1f}",
                action
            ]
            top10.append(row_data)
            sector_counts[r['Sec']] = sector_counts.get(r['Sec'], 0) + 1
            
        if len(top10) >= 12: break # A股龍頭較多，取前12

    tz = datetime.timezone(datetime.timedelta(hours=8))
    header_row1 = ["🇨🇳 A股 Master Sniper 成長領頭羊", "更新:", datetime.datetime.now(tz).strftime('%m-%d %H:%M'), "市場情緒:", f"{'偏暖' if m_change > 0 else '震盪'}", "戰略:", "右側跟蹤", "", "", "", "", ""]
    header_row2 = ["排名", "代碼", "板塊", "現價", "1D%", "ADR", "50MA乖離", "60日趨勢", "RPS總分", "評級指標", "綜合分", "作戰指令"]
    
    sync_to_google_sheet("🚀A股_動能成長", [header_row1, header_row2] + top10)

if __name__ == "__main__":
    run_a_right_side_momentum()
