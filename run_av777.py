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
# 1. 配置中心 (精選 A 股龍頭池)
# ==========================================
WEBAPP_URL = "你的_GOOGLE_SCRIPT_URL" 

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
# 2. 核心算法工具箱
# ==========================================
def sync_to_google_sheet(sheet_name, matrix):
    try:
        def safe_json_val(val):
            if isinstance(val, float) and not math.isfinite(val): return 0
            return str(val)
        payload = {"sheet_name": sheet_name, "data": json.loads(json.dumps(matrix, default=safe_json_val))}
        requests.post(WEBAPP_URL, json=payload, timeout=30)
        print(f"🎉 [先勝後戰 V81.3] 同步成功")
    except Exception as e: 
        print(f"❌ 同步失敗: {e}")

def format_a_tickers(ticker_list):
    formatted = []
    for t in ticker_list:
        t_str = str(t).strip().zfill(6)
        display_code = f"'{t_str}"
        yf_code = f"{t_str}.SS" if t_str.startswith(('6', '9')) else f"{t_str}.SZ"
        formatted.append((display_code, yf_code))
    return list(set(formatted))

def safe_get(d, k, def_v=0):
    v = d.get(k)
    return float(v) if v is not None else def_v

# ==========================================
# 3. 先勝邏輯：深度掃描與標準化評分
# ==========================================
def analyze_winning_potential(c):
    try:
        time.sleep(0.05)
        info = yf.Ticker(c['YF_T']).info
        sec = info.get('sector', '其他')
        
        if any(ex.lower() in sec.lower() for ex in EXCLUDED_INDUSTRIES): return None
        
        # 1. 基本面去噪評分
        rev_g = max(-20, min(safe_get(info, 'revenueGrowth') * 100, 150))
        op_m = max(-10, min(safe_get(info, 'operatingMargins') * 100, 50))
        # 修正：基本面分數權重，防止溢出
        f_score = (rev_g * 0.4 + op_m * 0.6) 

        # 2. 技術形態評分 (先勝關鍵：收縮與貼線)
        dist_to_ema20 = abs(c['P'] - c['EMA20']) / c['P'] * 100
        tech_bonus = 0
        if c['Tight'] < 2.0: tech_bonus += 25  # 超窄幅橫盤
        if dist_to_ema20 < 1.2: tech_bonus += 20 # 貼合支撐
        if c['Bias'] > 18: tech_bonus -= 40    # 嚴重超買

        # 3. 綜合歸一化分數 (目標範圍 0-100)
        # RPS權重 50%, 基本面權重 20%, 技術加成 30%
        final_score = (c['RPS_Rank'] * 0.5) + (min(f_score, 50) * 0.4) + tech_bonus
        
        c['Score'] = max(10, min(100, round(final_score, 1)))
        
        # 中文化板塊
        sec_map = {'Technology': '科技', 'Consumer Cyclical': '週期消費', 'Consumer Defensive': '防禦消費', 
                   'Healthcare': '醫療醫藥', 'Industrials': '工業製造', 'Basic Materials': '基礎材料', 
                   'Utilities': '公用事業', 'Energy': '能源'}
        c['Sec'] = sec_map.get(sec, sec[:4])
        c['Msg'] = f"增長:{rev_g:.0f}%/利潤:{op_m:.1f}%"
        
        return c
    except: return None

# ==========================================
# 4. 🚀 主引擎
# ==========================================
def run_master_sniper_a_v813():
    print("🚀 [先勝後戰 V81.3] 大師優化版啟動...")
    
    ticker_pairs = format_a_tickers(CORE_UNIVERSE)
    yf_codes = [p[1] for p in ticker_pairs]
    
    data = yf.download(yf_codes, period="1y", progress=False, group_by='ticker')
    
    raw_candidates = []
    for display_t, yf_t in ticker_pairs:
        try:
            df = data[yf_t].dropna()
            if len(df) < 150: continue
            
            close = df['Close']
            curr_p = close.iloc[-1]
            ma50 = close.rolling(50).mean().iloc[-1]
            ma200 = close.rolling(200).mean().iloc[-1]
            
            # 趨勢初步過濾：50日線上方，且200日線不掉頭
            if curr_p < ma50 or ma50 < ma200 * 0.92: continue
            
            # 計算混合回報（用於計算 RPS 排名）
            ret_short = (curr_p / close.iloc[-21]) - 1
            ret_long = (curr_p / close.iloc[-121]) - 1
            combined_ret = ret_short * 0.4 + ret_long * 0.6

            tightness = (close.tail(15).std() / close.tail(15).mean()) * 100
            
            prices_str = ",".join([str(round(p, 2)) for p in close.tail(50).tolist()])
            sparkline = f'=SPARKLINE({{{prices_str}}}, {{"charttype","line";"color","#E74C3C"}})'

            raw_candidates.append({
                "T": display_t, "YF_T": yf_t, "P": curr_p, "Raw_Ret": combined_ret,
                "1D": (curr_p/close.iloc[-2]-1)*100,
                "Bias": (curr_p/ma50 - 1)*100,
                "EMA20": close.ewm(span=20).mean().iloc[-1],
                "ADR": ((df['High']-df['Low'])/df['Low']).tail(15).mean()*100,
                "Tight": tightness, "Trend": sparkline
            })
        except: continue

    # --- 重要：計算 RPS 百分位排名 ---
    if not raw_candidates: return
    ret_values = [x['Raw_Ret'] for x in raw_candidates]
    for c in raw_candidates:
        # 計算百分比排名 (0-100)
        c['RPS_Rank'] = sum(1 for r in ret_values if r <= c['Raw_Ret']) / len(ret_values) * 100

    # 挑選 RPS 強勢股進行基本面深度分析
    top_momentum = sorted(raw_candidates, key=lambda x: x['RPS_Rank'], reverse=True)[:45]
    
    final_list = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(analyze_winning_potential, top_momentum)
        for r in results:
            if r: final_list.append(r)

    # 最終按綜合分數排序
    sorted_final = sorted(final_list, key=lambda x: x['Score'], reverse=True)
    
    table_data = []
    for r in sorted_final:
        # 更加精確的作戰指令
        dist_ema20 = abs(r['P'] - r['EMA20']) / r['P'] * 100
        if r['Score'] >= 85 and dist_ema20 < 1.5:
            action = "🔥 絕對勝算 (重倉)"
        elif r['Score'] >= 75 and r['Tight'] < 2.0:
            action = "🎯 蓄勢待發 (準備)"
        elif r['Bias'] > 16:
            action = "⏳ 乖離過大 (禁追)"
        elif r['Score'] < 40:
            action = "🧊 弱勢整理"
        else:
            action = "趨勢追蹤"

        table_data.append([
            f"SNIPER", r['T'], r['Sec'], round(r['P'], 2),
            f"{r['1D']:.1f}%", f"{r['ADR']:.1f}%", f"{r['Bias']:.1f}%",
            r['Trend'], f"{r['RPS_Rank']:.0f}", r['Msg'], r['Score'], action
        ])
        if len(table_data) >= 12: break

    tz = datetime.timezone(datetime.timedelta(hours=8))
    header1 = ["🏰 先勝後戰 A股 Sniper V81.3", "更新:", datetime.datetime.now(tz).strftime('%m-%d %H:%M'), "核心思想:", "不勝不戰", "技術重點:", "VCP收縮", "", "", "", "", ""]
    header2 = ["狀態", "代碼", "板塊", "現價", "1D%", "ADR", "50MA乖離", "50日趨勢", "RPS排名", "基本面透視", "綜合勝率", "作戰指令"]
    
    sync_to_google_sheet("🚀A股_先勝後戰", [header1, header2] + table_data)

if __name__ == "__main__":
    run_master_sniper_a_v813()
