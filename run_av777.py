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
# 1. 配置中心 (請務必填入你的 Google URL)
# ==========================================
# 填入你之前在 Google Apps Script 獲取的網址
WEBAPP_URL = "https://script.google.com/macros/s/AKfycbw_f6Uy1OMIIl-4mLsAaxe1rXr64qYf2j0RHoKl3-xu0QOp-5kqFpk9rTBIV9Yf5-kz/exec" 

# A 股核心戰略池 (精選各賽道最強龍頭)
CORE_UNIVERSE = [
    "600519", "601318", "000858", "600036", "600900", "000333", "601012", "300750", 
    "300760", "600276", "601888", "002594", "002475", "603259", "002714", "601899", 
    "603288", "600585", "600309", "002415", "600104", "002352", "000001", "600887", 
    "600690", "000651", "000725", "601668", "300059", "300413", "300124", "600438",
    "002142", "601919", "600941", "603501", "002460", "600111", "002466", "603986",
    "603659", "300274", "002812", "600406", "600031", "601100", "603806", "002459"
]

EXCLUDED_INDUSTRIES = ['Banks', 'Insurance', 'Financial Services']

# ==========================================
# 2. 核心計算引擎 (RPS 與 VCP)
# ==========================================
def sync_to_google_sheet(sheet_name, matrix):
    try:
        def safe_json_val(val):
            if isinstance(val, float) and not math.isfinite(val): return 0
            return str(val)
        payload = {"sheet_name": sheet_name, "data": json.loads(json.dumps(matrix, default=safe_json_val))}
        r = requests.post(WEBAPP_URL, json=payload, timeout=30)
        print(f"✅ 同步成功 | 響應: {r.text}")
    except Exception as e: 
        print(f"❌ 同步失敗: {e}")

def format_a_tickers(ticker_list):
    formatted = []
    for t in ticker_list:
        t_str = str(t).strip().zfill(6)
        display_code = f"'{t_str}" # 強制字符串防止吞零
        yf_code = f"{t_str}.SS" if t_str.startswith(('6', '9')) else f"{t_str}.SZ"
        formatted.append((display_code, yf_code))
    return list(set(formatted))

def analyze_stock(c):
    """先勝後戰：深度分析邏輯"""
    try:
        time.sleep(0.05)
        info = yf.Ticker(c['YF_T']).info
        sec = info.get('sector', '其他')
        
        if any(ex.lower() in sec.lower() for ex in EXCLUDED_INDUSTRIES): return None
        
        # 營收與利潤去噪處理
        rev_g = max(-20, min(safe_get(info, 'revenueGrowth') * 100, 150))
        op_m = max(-10, min(safe_get(info, 'operatingMargins') * 100, 50))
        
        # 計算綜合分數 (RPS佔50%, 基本面佔20%, 技術加成佔30%)
        dist_ema20 = abs(c['P'] - c['EMA20']) / c['P'] * 100
        tech_bonus = 0
        if c['Tight'] < 2.0: tech_bonus += 25  # VCP特徵：縮量
        if dist_ema20 < 1.5: tech_bonus += 15 # 支撐位
        if c['Bias'] > 18: tech_bonus -= 40    # 追高風險

        final_score = (c['RPS_Rank'] * 0.5) + (min(rev_g + op_m, 50) * 0.4) + tech_bonus
        
        c['Score'] = max(10, min(100, round(final_score, 1)))
        
        # 中文標籤
        sec_map = {'Technology': '科技', 'Consumer Cyclical': '週期消費', 'Consumer Defensive': '防禦消費', 
                   'Healthcare': '醫療', 'Industrials': '工業', 'Basic Materials': '材料'}
        c['Sec'] = sec_map.get(sec, sec[:4])
        c['Msg'] = f"G:{rev_g:.0f}%/M:{op_m:.0f}%"
        
        return c
    except: return None

def safe_get(d, k, def_v=0):
    v = d.get(k)
    return float(v) if v is not None else def_v

# ==========================================
# 3. 🚀 主程序
# ==========================================
def main():
    print("\n" + "="*40)
    print("🔥 [先勝後戰 V81.3 實戰版] 啟動...")
    print("="*40)
    
    ticker_pairs = format_a_tickers(CORE_UNIVERSE)
    yf_codes = [p[1] for p in ticker_pairs]
    
    print(f"📡 正在下載 {len(yf_codes)} 隻龍頭股數據...")
    data = yf.download(yf_codes, period="1y", progress=False, group_by='ticker')
    
    candidates = []
    for display_t, yf_t in ticker_pairs:
        try:
            df = data[yf_t].dropna()
            if len(df) < 150: continue
            
            close = df['Close']
            curr_p = close.iloc[-1]
            ma50 = close.rolling(50).mean().iloc[-1]
            
            # 右側過濾：必須在 50 日線上方
            if curr_p < ma50: continue
            
            # 計算混合動能回報
            ret_short = (curr_p / close.iloc[-21]) - 1
            ret_long = (curr_p / close.iloc[-121]) - 1
            combined_ret = ret_short * 0.4 + ret_long * 0.6

            # VCP 緊湊度 (過去 15 天波動率)
            tightness = (close.tail(15).std() / close.tail(15).mean()) * 100
            
            # 趨勢線指令
            prices_str = ",".join([str(round(p, 2)) for p in close.tail(50).tolist()])
            sparkline = f'=SPARKLINE({{{prices_str}}}, {{"charttype","line";"color","#E74C3C"}})'

            candidates.append({
                "T": display_t, "YF_T": yf_t, "P": curr_p, "Raw_Ret": combined_ret,
                "1D": (curr_p/close.iloc[-2]-1)*100,
                "Bias": (curr_p/ma50 - 1)*100,
                "EMA20": close.ewm(span=20).mean().iloc[-1],
                "ADR": ((df['High']-df['Low'])/df['Low']).tail(15).mean()*100,
                "Tight": tightness, "Trend": sparkline
            })
        except: continue

    # 計算 RPS 排名 (0-100)
    if not candidates: 
        print("❌ 沒有符合基礎過濾條件的股票")
        return
    
    all_rets = [x['Raw_Ret'] for x in candidates]
    for c in candidates:
        c['RPS_Rank'] = sum(1 for r in all_rets if r <= c['Raw_Ret']) / len(all_rets) * 100

    print(f"🔬 正在進行基本面與 VCP 深度分析...")
    final_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        for r in executor.map(analyze_stock, sorted(candidates, key=lambda x: x['RPS_Rank'], reverse=True)[:40]):
            if r: final_results.append(r)

    # 排序並格式化輸出
    final_results = sorted(final_results, key=lambda x: x['Score'], reverse=True)
    
    rows = []
    for r in final_results[:12]:
        dist = abs(r['P'] - r['EMA20']) / r['P'] * 100
        if r['Score'] >= 85 and dist < 1.5:
            action = "🔥 先勝之姿 (狙擊)"
        elif r['Tight'] < 2.0:
            action = "🎯 縮量蓄勢 (關注)"
        elif r['Bias'] > 16:
            action = "⏳ 乖離過大 (禁追)"
        else:
            action = "趨勢跟蹤"

        rows.append([
            "SNIPER", r['T'], r['Sec'], round(r['P'], 2),
            f"{r['1D']:.1f}%", f"{r['ADR']:.1f}%", f"{r['Bias']:.1f}%",
            r['Trend'], f"{r['RPS_Rank']:.0f}", r['Msg'], r['Score'], action
        ])

    # 同步
    tz = datetime.timezone(datetime.timedelta(hours=8))
    h1 = ["🏰 先勝後戰 A股 Sniper V81.3", "更新:", datetime.datetime.now(tz).strftime('%m-%d %H:%M'), "戰略:", "勝於易勝", "關鍵:", "RPS排名+VCP", "", "", "", "", ""]
    h2 = ["狀態", "代碼", "板塊", "現價", "1D%", "ADR", "50MA乖離", "50日趨勢", "RPS排名", "利潤/成長", "勝率分", "作戰指令"]
    
    sync_to_google_sheet("🚀A股_先勝後戰", [h1, h2] + rows)

if __name__ == "__main__":
    main()
