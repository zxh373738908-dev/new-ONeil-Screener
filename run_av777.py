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
# 1. 配置中心 (核心 A 股池)
# ==========================================
WEBAPP_URL = "你的_GOOGLE_SCRIPT_URL" 

# A 股戰略核心池 (包含各賽道真正具有「勝算」的領頭羊)
CORE_UNIVERSE = [
    "600519", "601318", "000858", "600036", "600900", "000333", "601012", "300750", 
    "300760", "600276", "601888", "002594", "002475", "603259", "002714", "601899", 
    "603288", "600585", "600309", "002415", "600104", "002352", "000001", "600887", 
    "600690", "000651", "000725", "601668", "300059", "300413", "300124", "600438",
    "002142", "601919", "600941", "603501", "002460", "600111", "002466", "603986"
]

# 排除行業：銀行、保險、地產及純金融租賃
EXCLUDED_INDUSTRIES = ['Banks', 'Insurance', 'Real Estate', 'Financial Services']

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
        print(f"🎉 [先勝後戰] 同步成功 -> [{sheet_name}]")
    except Exception as e: 
        print(f"❌ 同步失敗: {e}")

def format_a_tickers(ticker_list):
    """精確處理 A 股代碼，確保 Google Sheet 顯示領先零"""
    formatted = []
    for t in ticker_list:
        t_str = str(t).strip().zfill(6)
        display_code = f"'{t_str}" # 強制轉為字符串
        yf_code = f"{t_str}.SS" if t_str.startswith(('6', '9')) else f"{t_str}.SZ"
        formatted.append((display_code, yf_code))
    return list(set(formatted))

# ==========================================
# 3. 先勝邏輯：基本面與技術面深度掃描
# ==========================================
def analyze_winning_potential(c):
    """
    先勝後戰邏輯：
    1. 基本面不敗 (Revenue/Margin)
    2. 趨勢已勝 (RPS > 80, Above 50MA)
    3. 等待時機 (Low Tightness / Near EMA20)
    """
    try:
        time.sleep(0.05)
        ticker = yf.Ticker(c['YF_T'])
        info = ticker.info
        sec = info.get('sector', '未知')
        
        # 行業過濾
        if any(ex.lower() in sec.lower() for ex in EXCLUDED_INDUSTRIES): return None
        
        # 數據清洗 (去噪)
        rev_g = max(-20, min(safe_get(info, 'revenueGrowth') * 100, 150)) # 封頂 150%
        op_m = max(-10, min(safe_get(info, 'operatingMargins') * 100, 60)) # 封頂 60%
        div_y = safe_get(info, 'dividendYield') * 100
        
        # 計算「先勝」分數
        is_tech = 'Technology' in sec or 'Electronics' in sec or 'Communication' in sec
        fundamental_score = (rev_g * 0.6 + op_m * 0.4) if is_tech else (op_m + div_y * 2)
        
        # 技術面修正
        dist_to_ema20 = abs(c['P'] - c['EMA20']) / c['P'] * 100
        
        # 綜合評價分數 (基礎 50 分)
        final_score = 50 + (c['RPS'] * 0.3) + (fundamental_score * 0.2)
        
        # 加減分項：體現「先勝」哲學
        if c['Tight'] < 2.5: final_score += 15  # 窄幅橫盤是力量蓄積 (VCP)
        if dist_to_ema20 < 1.5: final_score += 15 # 貼線，回報比極高
        if c['Bias'] > 15: final_score -= 30    # 乖離過大，已非「先勝」而是冒險
        
        c['Score'] = max(10, round(final_score, 1))
        c['Sec'] = sec.replace('Technology', '科技').replace('Consumer', '消費').replace('Healthcare', '醫療')
        c['Msg'] = f"G:{rev_g:.0f}%/M:{op_m:.0f}%"
        
        return c
    except: return None

def safe_get(d, k, def_v=0):
    v = d.get(k)
    return float(v) if v is not None else def_v

# ==========================================
# 4. 🚀 主引擎
# ==========================================
def run_master_sniper_a():
    print("="*30)
    print("🚀 [先勝後戰 V81.2] 啟動...")
    
    ticker_pairs = format_a_tickers(CORE_UNIVERSE)
    yf_codes = [p[1] for p in ticker_pairs]
    
    # 一次性下載數據
    data = yf.download(yf_codes, period="1y", progress=False, group_by='ticker')
    
    initial_candidates = []
    for display_t, yf_t in ticker_pairs:
        try:
            df = data[yf_t].dropna()
            if len(df) < 100: continue
            
            close = df['Close']
            curr_p = close.iloc[-1]
            ma50 = close.rolling(50).mean().iloc[-1]
            ma200 = close.rolling(200).mean().iloc[-1]
            
            # 【先勝】技術過濾器：只看趨勢向上的龍頭
            if curr_p < ma50 or ma50 < ma200 * 0.95: continue
            
            # 計算相對強度 RPS (20日 & 120日 混合)
            ret20 = (curr_p / close.iloc[-21]) - 1
            ret120 = (curr_p / close.iloc[-121]) - 1
            raw_rps = (ret20 * 0.4 + ret120 * 0.6) * 100

            # VCP 緊湊度計算 (過去15天波動)
            tightness = (close.tail(15).std() / close.tail(15).mean()) * 100

            prices_str = ",".join([str(round(p, 2)) for p in close.tail(50).tolist()])
            sparkline = f'=SPARKLINE({{{prices_str}}}, {{"charttype","line";"color","#E74C3C"}})'

            initial_candidates.append({
                "T": display_t, "YF_T": yf_t, "P": curr_p, "RPS": raw_rps,
                "1D": (curr_p/close.iloc[-2]-1)*100,
                "Bias": (curr_p/ma50 - 1)*100,
                "EMA20": close.ewm(span=20).mean().iloc[-1],
                "ADR": ((df['High']-df['Low'])/df['Low']).tail(15).mean()*100,
                "Tight": tightness, "Trend": sparkline
            })
        except: continue

    # 排序取 RPS 領先者進行基本面深度掃描
    top_momentum = sorted(initial_candidates, key=lambda x: x['RPS'], reverse=True)[:40]
    
    final_list = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(analyze_winning_potential, top_momentum)
        for r in results:
            if r: final_list.append(r)

    # 按綜合分數排序
    sorted_final = sorted(final_list, key=lambda x: x['Score'], reverse=True)
    
    table_data = []
    for r in sorted_final:
        # 動態作戰指令
        dist_to_ema20 = abs(r['P'] - r['EMA20']) / r['P'] * 100
        if r['Score'] > 85 and dist_to_ema20 < 1.5:
            action = "🔥 先勝之姿 (狙擊)"
        elif r['Bias'] > 15:
            action = "⌛ 已過買點 (觀望)"
        elif r['Tight'] < 2.0:
            action = "🕯️ 縮量靜默 (蓄勢)"
        else:
            action = "跟隨趨勢"

        table_data.append([
            f"SNIPER", r['T'], r['Sec'], round(r['P'], 2),
            f"{r['1D']:.1f}%", f"{r['ADR']:.1f}%", f"{r['Bias']:.1f}%",
            r['Trend'], f"{r['RPS']:.1f}", r['Msg'], r['Score'], action
        ])
        if len(table_data) >= 12: break

    # 寫入 Google Sheets
    tz = datetime.timezone(datetime.timedelta(hours=8))
    header1 = ["🏰 先勝後戰 A股大師策略 V81.2", "更新:", datetime.datetime.now(tz).strftime('%m-%d %H:%M'), "核心思想:", "勝於易勝者", "風險控制:", "嚴控乖離", "", "", "", "", ""]
    header2 = ["狀態", "代碼", "板塊", "現價", "1D%", "ADR", "50MA乖離", "50日趨勢", "RPS強度", "利潤成長", "勝率分", "作戰指令"]
    
    sync_to_google_sheet("🚀A股_先勝後戰", [header1, header2] + table_data)

if __name__ == "__main__":
    run_master_sniper_a()
