import yfinance as yf
import pandas as pd
import numpy as np
import datetime, requests, json, warnings, uuid
from datetime import timezone, timedelta
from concurrent.futures import ThreadPoolExecutor

warnings.filterwarnings('ignore')

# ==========================================
# 1. 配置中心與行業映射
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycbyYfpfYNyRhXcyZrfIHEyErECMM82xkCKfZm71RUZ1YL6Xjr5Kca3ruoVJzxcNAwH9q/exec"
BASE_DATE = "2024-12-31" 

SECTOR_MAP = {
    "300502": "半導體", "300308": "半導體", "300394": "半導體", "688313": "半導體", "688041": "半導體", "603501": "半導體",
    "300750": "新能源", "002594": "新能源", "002475": "蘋果鏈", "002371": "特高壓",
    "600519": "白酒消費", "000333": "家電消費", "000951": "汽車配件",
    "601899": "有色資源", "601857": "石油石化", "601208": "工業金屬", "600105": "永磁資源",
    "600030": "金融證券", "002428": "綜合航運", "003031": "智能製造", 
    "601138": "算力/富聯", "603259": "醫療/藥明", "002222": "豬肉養殖", "603799": "鋰電材料"
}

CORE_TICKERS_RAW = list(SECTOR_MAP.keys())

def format_ticker(code):
    c = str(code).zfill(6)
    return f"{c}.SS" if c.startswith('6') else f"{c}.SZ"

def safe_convert(obj):
    if isinstance(obj, (np.integer, np.floating)): 
        return float(obj) if not np.isnan(obj) else 0.0
    return str(obj)

# 獨立提取：獲取市值的函數 (用於多線程併發)
def fetch_mcap(t_full):
    try:
        mcap_raw = yf.Ticker(t_full).fast_info.get('marketCap', 0)
        return f"{mcap_raw / 1e9:.1f}B" if mcap_raw > 0 else "N/A"
    except:
        return "N/A"

# ==========================================
# 2. 全景分析引擎 (V60.26 先勝後戰 戰術版)
# ==========================================
def analyze_v26_tactical(data, bench_series, tickers_raw, mcaps_dict):
    all_results = []
    base_dt_parsed = pd.to_datetime(f"{BASE_DATE} 23:59:59")
    
    def get_ret(ser, d): 
        if len(ser) < 2: return 0.0
        safe_d = min(len(ser) - 1, d)
        return (ser.iloc[-1] / ser.iloc[-safe_d - 1]) - 1

    # 預計算行業均值
    sector_perf = {}
    for t_raw in tickers_raw:
        try:
            c = data[format_ticker(t_raw)]['Close'].dropna()
            if len(c) >= 2:
                daily_ret = (c.iloc[-1] / c.iloc[-2] - 1) * 100
                s_name = SECTOR_MAP.get(t_raw, "其它")
                sector_perf.setdefault(s_name, []).append(daily_ret)
        except KeyError: continue
    
    sector_avg = {k: np.mean(v) for k, v in sector_perf.items()}

    # 核心計算
    for t_raw in tickers_raw:
        t_full = format_ticker(t_raw)
        try:
            df = data[t_full].ffill().dropna()
            if len(df) < 120: continue # 確保有足夠K線計算 120日成本線
            
            c, h, l, v = df['Close'], df['High'], df['Low'], df['Volume']
            curr_price = float(c.iloc[-1])
            prev_price = float(c.iloc[-2])
            
            # --- 【先勝後戰核心】籌碼成本線計算 ---
            # 戰略線：120日量價加權成本 (近似 CYC 無窮成本線)
            vwma_120 = (c * v).tail(120).sum() / v.tail(120).sum()
            
            # 戰術線：20日機構滾動成本 (VWAP 加權均線)
            vwma_20 = (c * v).tail(20).sum() / v.tail(20).sum()
            
            # 乖離率 (升級為距離 20日主力成本的距離)
            bias_vwma20 = ((curr_price - vwma_20) / vwma_20) * 100
            
            # --- 基礎指標 ---
            ret_1d = (curr_price / prev_price - 1) * 100
            adr = ((h / l - 1).tail(20).mean()) * 100
            vol_mean_20 = v.tail(20).mean()
            vol_ratio = v.iloc[-1] / vol_mean_20 if vol_mean_20 != 0 else 1.0
            
            # 繪圖
            prices_60_str = ",".join(c.tail(60).round(2).astype(str).tolist())
            chart_formula = f'=SPARKLINE(SPLIT("{prices_60_str}", ","))'
            
            # 行業共振
            s_name = SECTOR_MAP.get(t_raw, "其它")
            s_avg_ret = sector_avg.get(s_name, 0)
            resonance_str = f"{s_name}({s_avg_ret:+.1f}%)"
            
            # 相對強度 (REL)
            r20, r60, r120 = get_ret(c, 20)*100, get_ret(c, 60)*100, get_ret(c, 120)*100
            rel5 = get_ret(c, 5)*100 - get_ret(bench_series, 5)*100
            rel20 = r20 - get_ret(bench_series, 20)*100
            rel60 = r60 - get_ret(bench_series, 60)*100
            rel120 = r120 - get_ret(bench_series, 120)*100
            
            # 基礎收益
            target_dt = base_dt_parsed.tz_localize(c.index.tz) if c.index.tz else base_dt_parsed
            past_data = c[c.index <= target_dt]
            ret_base = ((curr_price / past_data.iloc[-1]) - 1) * 100 if not past_data.empty else 0.0

            # --- 【先勝後戰】戰術動作判定引擎 ---
            tactical_action = "⚪ 觀望待機"
            is_bull_trend = curr_price > vwma_120 # 大趨勢：必須站在全換手成本線之上
            recent_high = h.tail(5).max() # 近5日最高價，判斷是否剛突破過
            
            if is_bull_trend:
                # 戰術 A: 🎯 黑線回踩狙擊 (勝率最高：突破後縮量回調至 20日 VWAP 不破)
                if (recent_high > h.iloc[-1]) and (vol_ratio < 1.0) and (abs(bias_vwma20) <= 1.5) and (curr_price >= vwma_20):
                    tactical_action = "🎯 回踩狙擊(勝)"
                    
                # 戰術 B: 🚀 帶量突破強攻 (右側強勢：放量大陽線上穿 20日 VWAP)
                elif (vol_ratio > 1.5) and (ret_1d > 2.5) and (prev_price <= vwma_20) and (curr_price > vwma_20):
                    tactical_action = "🚀 放量強攻(勝)"
                    
                # 戰術 C: 🛡️ 安全持倉區 (乖離不大，順勢而為)
                elif curr_price > vwma_20 and bias_vwma20 < 8.0:
                    tactical_action = "🛡️ 均線上持倉"
                    
                # 戰術 D: ⚠️ 乖離過大風險 (主力大幅獲利，隨時可能砸盤洗盤)
                elif bias_vwma20 >= 8.0:
                    tactical_action = "⚠️ 乖離過大(勿追)"
            else:
                # 熊市戰術 (只做深度超跌反抽)
                if bias_vwma20 < -10.0 and ret_1d > 2.0:
                    tactical_action = "🟢 深度超跌反擊"

            # 模型得分
            score = rel20 * 0.4 + rel60 * 0.3 + rel120 * 0.3 + 100
            
            all_results.append({
                "Ticker": t_raw, "Industry": s_name, "Price": curr_price,
                "1D": ret_1d, "Resonance": resonance_str,
                "ADR": adr, "Vol_Ratio": vol_ratio, "Bias": bias_vwma20, # Bias已替換為VWMA20乖離
                "MktCap": mcaps_dict.get(t_full, "N/A"), "Score": score, "S_Avg": s_avg_ret,
                "REL5": rel5, "REL20": rel20, "REL60": rel60, "REL120": rel120,
                "R20": r20, "R60": r60, "R120": r120, "Base_Ret": ret_base,
                "Chart_60D": chart_formula,
                "Action": tactical_action # 替換為全新戰術標籤
            })
        except Exception as e: 
            continue
    
    return all_results

# ==========================================
# 3. 主流程與數據推流
# ==========================================
def main():
    tz = timezone(timedelta(hours=8))
    dt_str = datetime.datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
    trace_id = f"QNT-{uuid.uuid4().hex[:4].upper()}"
    
    print(f"🚀 V60.26 先勝後戰(戰術版) 啟動 | ID: {trace_id}")
    tickers_full = [format_ticker(t) for t in CORE_TICKERS_RAW]
    
    try:
        print("⏳ 正在獲取 K線歷史數據 (含 120日籌碼運算)...")
        data = yf.download(tickers_full, period="3y", group_by='ticker', threads=True, progress=False, auto_adjust=True)
        idx = yf.download("000300.SS", period="3y", threads=True, progress=False, auto_adjust=True)
        bench = idx['Close'].ffill().iloc[:,0] if isinstance(idx['Close'], pd.DataFrame) else idx['Close'].ffill()
        
        print("⏳ 正在併發獲取 股票市值...")
        with ThreadPoolExecutor(max_workers=10) as executor:
            mcaps_list = list(executor.map(fetch_mcap, tickers_full))
        mcaps_dict = dict(zip(tickers_full, mcaps_list))
        
    except Exception as e:
        print(f"❌ 數據獲取失敗: {e}"); return

    # 執行分析計算
    analysis_list = analyze_v26_tactical(data, bench, CORE_TICKERS_RAW, mcaps_dict)
    
    # 按 Score 從高到低排序
    analysis_list.sort(key=lambda x: x['Score'], reverse=True)
    total = len(analysis_list)
    
    rows = []
    for i, x in enumerate(analysis_list):
        rank = int((total - i) / total * 100) if total > 0 else 0
        
        # 格式化組裝
        rows.append([
            x['Ticker'], 
            x['Industry'], 
            round(x['Score'], 1), 
            f"{x['1D']:+.2f}%", 
            x['Chart_60D'], 
            x['Action'],           # 全新輸出的戰術動作信號
            x['Resonance'], 
            f"{x['ADR']:.2f}%", 
            f"{x['Vol_Ratio']:.2f}", 
            f"{x['Bias']:+.2f}%",  # 此處的Bias已是基於主力成本的乖離率
            x['MktCap'], 
            rank, 
            f"{x['REL5']:+.2f}%", 
            f"{x['REL20']:+.2f}%", 
            f"{x['REL60']:+.2f}%", 
            f"{x['REL120']:+.2f}%", 
            f"{x['R20']:+.2f}%", 
            f"{x['R60']:+.2f}%", 
            f"{x['R120']:+.2f}%", 
            x['Price'], 
            f"{x['Base_Ret']:+.2f}%"
        ])

    # 總裝 Google Sheets 數據
    meta_row = ["📊 V60.26 先勝後戰版(籌碼成本)", "ID:", trace_id, "模式:", "Sector & VWAP", "更新:", dt_str] + [""] * 14
    
    # 將欄位名稱 Bias 修改為 Bias(VWMA)，提醒您這是距離主力成本線的距離
    col_names = [
        "Ticker", "Industry", "Score", "1D%", "近60日趨勢(圖)", "Action", "Resonance", 
        "ADR", "Vol_Ratio", "Bias(VWMA)", "MktCap", "Rank", "REL5", "REL20", "REL60", 
        "REL120", "R20", "R60", "R120", "Price", f"From {BASE_DATE}"
    ]
    
    payload_data = [meta_row, col_names] + rows

    try:
        print("📡 正在推流至 Google Sheets...")
        payload = json.loads(json.dumps(payload_data, default=safe_convert))
        resp = requests.post(WEBAPP_URL, json=payload, timeout=30)
        print(f"✅ 結果已推送 | Google 響應: {resp.text}")
    except: 
        print("❌ 推送失敗")

if __name__ == "__main__":
    main()
