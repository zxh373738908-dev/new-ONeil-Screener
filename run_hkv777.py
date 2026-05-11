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
# 1. 港股配置中心
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"

# 港股核心種子池 (互聯網、新勢力、高息中特估、醫藥、消費巨頭)
HK_MONOPOLY_TICKERS =[
    "0700", "3690", "9988", "1810", "1024", "9618", "9888", "1211", "2015", "9868", 
    "0883", "0857", "0386", "0941", "0762", "0005", "1299", "0388", "0293", "2020",
    "2359", "2269", "1093", "0853", "0981", "1347", "1818", "2899", "3993", "1928"
]

FALLBACK_UNIVERSE = HK_MONOPOLY_TICKERS +[
    "0968", "0268", "6690", "0175", "2382", "0066", "0002", "0003", "0011", "0012",
    "0288", "0316", "0322", "0522", "0772", "0868", "0992", "1044", "1109", "1113",
    "1177", "1997", "2313", "2318", "2333", "3328", "3968", "6618", "6862", "9999"
]

EXCLUDED_INDUSTRIES =['Banks', 'Insurance', 'Real Estate']
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
        print(f"🎉 同步成功 -> [{sheet_name}]")
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

def format_hk_tickers(ticker_list):
    return list(set([f"{str(t).strip().split('.')[0].zfill(4)}.HK" for t in ticker_list]))

# ==========================================
# 3. 基本面併發獲取引擎 (V80.9 優化)
# ==========================================
def fetch_fundamental_data(c):
    """多線程抓取單檔股票的基本面信息，大幅提升整體速度"""
    try:
        time.sleep(0.1) # 輕微延遲，防止 Yahoo Finance 429 擋 IP
        info = yf.Ticker(c['YF_T']).info
        sec = str(info.get('sector', 'Unknown'))
        
        # 排除指定板塊
        if any(ex.lower() in sec.lower() for ex in EXCLUDED_INDUSTRIES): return None
        
        rev_g = safe_get(info, 'revenueGrowth') * 100
        op_m = safe_get(info, 'operatingMargins') * 100
        div_yield = safe_get(info, 'dividendYield') * 100
        is_tech = 'Technology' in sec or 'Communication' in sec or 'Software' in str(info.get('industry', ''))
        
        # 港股特色基本面評分邏輯
        if is_tech:
            fin_score, msg_prefix = rev_g + op_m, "R40"
        elif div_yield > 4.0:
            fin_score, msg_prefix = op_m + div_yield * 2, f"高息({div_yield:.1f}%)"
        else:
            fin_score, msg_prefix = op_m + rev_g, "利潤"
            
        if fin_score > 0 or c['RPS'] > 85:
            c['Sec'] = sec[:10].replace('Consumer C', 'Cons.C').replace('Consumer D', 'Cons.D')
            c['Fin_S'] = fin_score
            c['Msg'] = f"{msg_prefix}({fin_score:.0f}%)" + (" 💎" if c['Tight'] < 3.5 else "")
            
            # --- 宗師「先勝後戰」評分核心 ---
            dist = abs(c['P'] - c['EMA20']) / c['P'] * 100
            score = (c['RPS'] * 0.5) + (min(fin_score, 100) * 0.15)
            
            # 技術面加減分
            if dist < 1.5: score += 40             # 狙擊位大加分
            if c['Bias'] > 15: score -= (c['Bias'] - 15) * 8 # 港股嚴懲追高
            if c['Tight'] < 3.0: score += 15       # 價格收斂加分
            if c['RVOL'] > 2.0: score += 10        # 爆量突破加分
            
            c['Score'], c['Dist'] = score, dist
            return c
    except: pass
    return None

# ==========================================
# 4. 🚀 主引擎: 港股 V80.9 先勝後戰版
# ==========================================
def run_hk_right_side_momentum():
    print("\n" + "="*50 + "\n🚀[策略 HK: V80.9 宗師極速優化版] 啟動...")
    
    try:
        vix = float(yf.download("^VHSI", period="5d", progress=False)['Close'].iloc[-1])
    except: 
        vix = 25.0 

    tickers = format_hk_tickers(FALLBACK_UNIVERSE)
    print(f"📡 正在掃描港股 {len(tickers)} 隻核心戰士...")
    data = yf.download(tickers, period="2y", interval="1d", group_by='ticker', auto_adjust=True, progress=False)
    
    stats_list =[]
    for t in tickers:
        df = extract_ticker_data(data, t)
        if df.empty or len(df) < 200: continue
        close, vol = df['Close'], df['Volume']
        
        # 流動性與仙股裝甲
        if close.iloc[-1] < 1.0 or vol.tail(10).mean() < 2000000: continue

        stats_list.append({
            "T": t.replace('.HK', ''), "YF_T": t, "df": df, "close": close, "vol": vol,
            "r20": calculate_return(close, 20), "r60": calculate_return(close, 60),
            "r120": calculate_return(close, 120), "r250": calculate_return(close, 250)
        })
    
    if not stats_list:
        print("❌ 未抓取到有效數據。") return

    df_stats = pd.DataFrame(stats_list)
    for col, period in[('20R', 'r20'), ('60R', 'r60'), ('120R', 'r120')]:
        df_stats[col] = df_stats[period].rank(pct=True) * 100
        
    df_stats['RPS'] = (df_stats['20R'] * 0.3) + (df_stats['60R'] * 0.4) + (df_stats['120R'] * 0.3)

    # 1. 快速技術面初篩
    raw_cands =[]
    for _, row in df_stats.iterrows():
        df, close = row['df'], row['close']
        curr_p, ma50 = float(close.iloc[-1]), close.tail(50).mean()
        ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
        
        if row['RPS'] < 70 or curr_p < ma50: continue

        # 【視覺優化】：綠漲紅跌，使用經典多頭綠色 (#27AE60)
        sparkline_cmd = f'=SPARKLINE({{{",".join([str(round(p,2)) for p in close.tail(60).tolist()])}}}, {{"charttype","line";"color","#27AE60"}})'

        raw_cands.append({
            "T": row['T'], "YF_T": row['YF_T'], "P": curr_p, "RPS": row['RPS'], "EMA20": ema20,
            "1D": calculate_return(close, 1), "Bias": ((curr_p - ma50)/ma50)*100,
            "ADR": ((df['High']-df['Low'])/df['Low']).tail(20).mean()*100,
            "RVOL": float(row['vol'].iloc[-1] / max(row['vol'].tail(10).mean(), 1)),
            "Tight": float((close.tail(15).std() / close.tail(15).mean()) * 100),
            "Trend": sparkline_cmd
        })

    # 取 RPS 最高的前 65 檔
    top_cands = sorted(raw_cands, key=lambda x: x['RPS'], reverse=True)[:65]
    print(f"🔬 啟動多線程基本面掃描 (共 {len(top_cands)} 隻)，這將非常快...")

    # 2. 多線程併發獲取基本面 (提速核心)
    final_pool =[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(fetch_fundamental_data, top_cands)
        for res in results:
            if res is not None: final_pool.append(res)

    # 3. 戰略分級與輸出
    sorted_final = sorted(final_pool, key=lambda x: x['Score'], reverse=True)
    top10, sector_counts, sector_map =[], {}, {}
    
    # 統計板塊熱度
    for r in sorted_final: sector_map[r['Sec']] = sector_map.get(r['Sec'], 0) + 1

    for r in sorted_final:
        if sector_counts.get(r['Sec'], 0) < MAX_PER_SECTOR:
            if r['Bias'] > 18: action = "🚫 嚴禁追高(易被割)"
            elif r['Score'] > 80 and r['Dist'] < 2.0: action = "🔥 狙擊開火!"
            elif r['Bias'] < 8: action = "🎯 底部潛伏"
            else: action = f"觀察(距買點{r['Dist']:.1f}%)"
            
            t_display = ("🐺" if sector_map.get(r['Sec'], 0) >= 3 else "") + r['T']
            top10.append([
                f"T{len(top10)+1}", t_display, r['Sec'], round(r['P'], 2), f"{r['1D']:.1f}%", f"{r['ADR']:.1f}%",
                f"{r['Bias']:.1f}%", r['Trend'], f"{r['RPS']:.1f}", r['Msg'], f"{r['Score']:.1f}", action
            ])
            sector_counts[r['Sec']] = sector_counts.get(r['Sec'], 0) + 1
        if len(top10) >= 10: break

    # 寫入 Google Sheet
    tz = datetime.timezone(datetime.timedelta(hours=8))
    # 【戰略回歸】：先勝後戰
    header = [["🏰 V80.9 Master Sniper 港股先勝後戰版", "更新:", datetime.datetime.now(tz).strftime('%m-%d %H:%M'), "VHSI(恐慌):", f"{vix:.1f}", "戰略:", "先勝後戰", "", "", "", "", ""],["排名", "代碼", "板塊", "現價", "1D%", "ADR", "50MA乖離", "60日趨勢", "RPS總分", "基本面", "評分", "作戰指令"]
    ]
    sync_to_google_sheet("🚀港股_動能成長", header + top10)

if __name__ == "__main__":
    run_hk_right_side_momentum()
