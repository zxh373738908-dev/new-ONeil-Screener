import yfinance as yf
import pandas as pd
import numpy as np
import datetime, requests, json, warnings, uuid
from datetime import timezone, timedelta
from concurrent.futures import ThreadPoolExecutor

warnings.filterwarnings('ignore')

# ==========================================
# 1. 配置中心与行业映射
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycbyYfpfYNyRhXcyZrfIHEyErECMM82xkCKfZm71RUZ1YL6Xjr5Kca3ruoVJzxcNAwH9q/exec"
BASE_DATE = "2024-12-31" 

SECTOR_MAP = {
    "300502": "半导体", "300308": "半导体", "300394": "半导体", "688313": "半导体", "688041": "半导体", "603501": "半导体",
    "300750": "新能源", "002594": "新能源", "002475": "苹果链", "002371": "特高压",
    "600519": "白酒消费", "000333": "家电消费", "000951": "汽车配件",
    "601899": "有色资源", "601857": "石油石化", "601208": "工业金属", "600105": "永磁资源",
    "600030": "金融证券", "002428": "综合航运", "003031": "智能制造", 
    "601138": "算力/富联", "603259": "医疗/药明", "002222": "猪肉养殖", "603799": "锂电材料"
}

CORE_TICKERS_RAW = list(SECTOR_MAP.keys())

def format_ticker(code):
    c = str(code).zfill(6)
    return f"{c}.SS" if c.startswith('6') else f"{c}.SZ"

def safe_convert(obj):
    if isinstance(obj, (np.integer, np.floating)): 
        return float(obj) if not np.isnan(obj) else 0.0
    return str(obj)

# 独立提取：获取市值的函数 (用于多线程并发)
def fetch_mcap(t_full):
    try:
        mcap_raw = yf.Ticker(t_full).fast_info.get('marketCap', 0)
        return f"{mcap_raw / 1e9:.1f}B" if mcap_raw > 0 else "N/A"
    except:
        return "N/A"

# ==========================================
# 2. 全景分析引擎 (性能优化版)
# ==========================================
def analyze_v25(data, bench_series, tickers_raw, mcaps_dict):
    all_results =[]
    
    # 提前解析 Base Date (避免在循环中重复解析)
    base_dt_parsed = pd.to_datetime(f"{BASE_DATE} 23:59:59")
    
    # 辅助函数：安全计算周期涨幅
    def get_ret(ser, d): 
        if len(ser) < 2: return 0.0
        safe_d = min(len(ser) - 1, d)
        return (ser.iloc[-1] / ser.iloc[-safe_d - 1]) - 1

    # 步骤 A: 预计算行业均值
    sector_perf = {}
    for t_raw in tickers_raw:
        try:
            c = data[format_ticker(t_raw)]['Close'].dropna()
            if len(c) >= 2:
                daily_ret = (c.iloc[-1] / c.iloc[-2] - 1) * 100
                s_name = SECTOR_MAP.get(t_raw, "其它")
                sector_perf.setdefault(s_name,[]).append(daily_ret)
        except KeyError: continue
    
    sector_avg = {k: np.mean(v) for k, v in sector_perf.items()}

    # 步骤 B: 核心指标计算
    for t_raw in tickers_raw:
        t_full = format_ticker(t_raw)
        try:
            df = data[t_full].ffill().dropna()
            if len(df) < 20: continue
            
            c, h, l, v = df['Close'], df['High'], df['Low'], df['Volume']
            curr_price = float(c.iloc[-1])
            
            # --- 基础与趋势 ---
            ret_1d = (curr_price / c.iloc[-2] - 1) * 100
            ma20 = c.tail(20).mean()
            bias_20 = ((curr_price - ma20) / ma20) * 100
            
            # --- Pandas 向量化生成 60日微型走势图 ---
            # 优化点：使用 pandas 向量化代替 list comprehension，速度更快
            prices_60_str = ",".join(c.tail(60).round(2).astype(str).tolist())
            chart_formula = f'=SPARKLINE(SPLIT("{prices_60_str}", ","))'

            # --- 量价情绪指标 ---
            adr = ((h / l - 1).tail(20).mean()) * 100
            v_mean_20 = v.tail(20).mean()
            vol_ratio = v.iloc[-1] / v_mean_20 if v_mean_20 != 0 else 1.0
            
            # --- 行业共振 ---
            s_name = SECTOR_MAP.get(t_raw, "其它")
            s_avg_ret = sector_avg.get(s_name, 0)
            resonance_str = f"{s_name}({s_avg_ret:+.1f}%)"
            
            # --- 相对强度 (R & REL) ---
            r20, r60, r120 = get_ret(c, 20)*100, get_ret(c, 60)*100, get_ret(c, 120)*100
            rel5 = get_ret(c, 5)*100 - get_ret(bench_series, 5)*100
            rel20 = r20 - get_ret(bench_series, 20)*100
            rel60 = r60 - get_ret(bench_series, 60)*100
            rel120 = r120 - get_ret(bench_series, 120)*100
            
            # --- 时区安全的 Base Ret 计算 ---
            target_dt = base_dt_parsed.tz_localize(c.index.tz) if c.index.tz else base_dt_parsed
            past_data = c[c.index <= target_dt]
            ret_base = ((curr_price / past_data.iloc[-1]) - 1) * 100 if not past_data.empty else 0.0

            # --- 模型得分 ---
            score = rel20 * 0.4 + rel60 * 0.3 + rel120 * 0.3 + 100
            
            all_results.append({
                "Ticker": t_raw, "Industry": s_name, "Price": curr_price,
                "1D": ret_1d, "Resonance": resonance_str,
                "ADR": adr, "Vol_Ratio": vol_ratio, "Bias": bias_20,
                "MktCap": mcaps_dict.get(t_full, "N/A"), "Score": score, "S_Avg": s_avg_ret,
                "REL5": rel5, "REL20": rel20, "REL60": rel60, "REL120": rel120,
                "R20": r20, "R60": r60, "R120": r120, "Base_Ret": ret_base,
                "Chart_60D": chart_formula 
            })
        except Exception as e: 
            # 如果有问题静默跳过该标的，防止整个程序崩溃
            continue
    
    return all_results

# ==========================================
# 3. 主流程与数据推流
# ==========================================
def main():
    tz = timezone(timedelta(hours=8))
    dt_str = datetime.datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
    trace_id = f"QNT-{uuid.uuid4().hex[:4].upper()}"
    
    print(f"🚀 V60.25 增强面板启动 (优化版) | ID: {trace_id}")
    tickers_full =[format_ticker(t) for t in CORE_TICKERS_RAW]
    
    try:
        # 1. 批量下载K线历史数据 (threads=True 利用内部多线程)
        print("⏳ 正在获取 K线数据...")
        data = yf.download(tickers_full, period="3y", group_by='ticker', threads=True, progress=False, auto_adjust=True)
        idx = yf.download("000300.SS", period="3y", threads=True, progress=False, auto_adjust=True)
        bench = idx['Close'].ffill().iloc[:,0] if isinstance(idx['Close'], pd.DataFrame) else idx['Close'].ffill()
        
        # 2. 🚀 [多线程优化核心] 并发获取所有市值信息，耗时由20秒降至2秒
        print("⏳ 正在并发获取 股票市值...")
        with ThreadPoolExecutor(max_workers=10) as executor:
            mcaps_list = list(executor.map(fetch_mcap, tickers_full))
        mcaps_dict = dict(zip(tickers_full, mcaps_list))
        
    except Exception as e:
        print(f"❌ 数据获取失败: {e}"); return

    # 执行分析计算
    analysis_list = analyze_v25(data, bench, CORE_TICKERS_RAW, mcaps_dict)
    
    # 按 Score 从高到低排序
    analysis_list.sort(key=lambda x: x['Score'], reverse=True)
    total = len(analysis_list)
    
    rows =[]
    for i, x in enumerate(analysis_list):
        rank = int((total - i) / total * 100) if total > 0 else 0
        
        # Action (交易信号)
        action = "⚪ 观望"
        if x['S_Avg'] > 1.0 and rank >= 80: action = "🔥 强共振"
        elif x['S_Avg'] > 0.5 and rank >= 50: action = "✅ 联动"
        elif x['Bias'] < -8.0: action = "🟢 超跌"
        elif x['Vol_Ratio'] > 2.0 and x['1D'] > 3.0: action = "⚡ 异动"

        # 格式化组装
        rows.append([
            x['Ticker'], 
            x['Industry'], 
            round(x['Score'], 1), 
            f"{x['1D']:+.2f}%", 
            x['Chart_60D'], 
            action, 
            x['Resonance'], 
            f"{x['ADR']:.2f}%", 
            f"{x['Vol_Ratio']:.2f}", 
            f"{x['Bias']:+.2f}%", 
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

    # 组装 Google Sheets 需要的 Payload
    meta_row =["📊 V60.25 全景增强面板(优化)", "ID:", trace_id, "模式:", "Sector & RPS", "更新:", dt_str] + [""] * 14
    
    col_names =[
        "Ticker", "Industry", "Score", "1D%", "近60日趨勢(圖)", "Action", "Resonance", 
        "ADR", "Vol_Ratio", "Bias", "MktCap", "Rank", "REL5", "REL20", "REL60", 
        "REL120", "R20", "R60", "R120", "Price", f"From {BASE_DATE}"
    ]
    
    payload_data = [meta_row, col_names] + rows

    try:
        print("📡 正在推流至 Google Sheets...")
        payload = json.loads(json.dumps(payload_data, default=safe_convert))
        resp = requests.post(WEBAPP_URL, json=payload, timeout=30)
        print(f"✅ 结果已推送 | Google 响应: {resp.text}")
    except: 
        print("❌ 推送失败")

if __name__ == "__main__":
    main()
