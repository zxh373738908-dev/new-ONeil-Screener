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

FUTU_API_URL = "http://127.0.0.1:15000"
FUTU_API_TOKEN = "my_secret_token_2026"

# 👑 核心持倉 + 科技七姐妹 (Mag 7) + 強勢板塊龍頭
MASTER_CURRENT = ["AMD", "ARW", "ATI", "FTNT", "HPE", "HST", "STT", "VIK", "VSAT"]
MAG_7 = ["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA"]
SECTOR_LEADERS = ["FTI", "TDW", "PTEN", "VAL", "LBRT", "RIG", "NE", "BKR", "OIH", "XLE", "MU", "AMAT", "KLAC", "LRCX", "ADI", "DELL", "NTAP", "STX", "VLO"]

def get_universe():
    core_watchlist = list(set(MASTER_CURRENT + MAG_7 + SECTOR_LEADERS + [
        "JBHT", "PRM", "ROIV", "ROKU", "TRGP", "YOU", "DAL", "GEV", "IBKR", 
        "LLY", "MNST", "RDDT", "PWR", "IRDM", "QS", "VRT", "FSLR", "SNDK", "QQQ"
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
        time.sleep(random.uniform(0.03, 0.06))
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

def fetch_futu_capital_flow(t):
    futu_code = f"US.{t.replace('-', '.')}"
    url = f"{FUTU_API_URL}/api/stock/capital_distribution?code={futu_code}"
    headers = {"Authorization": f"Bearer {FUTU_API_TOKEN}"}
    try:
        res = requests.get(url, headers=headers, timeout=1.5).json()
        if res and isinstance(res, list) and len(res) > 0:
            d = res[0]
            super_net = (d.get('capital_in_super', 0) - d.get('capital_out_super', 0)) / 1e4
            big_net = (d.get('capital_in_big', 0) - d.get('capital_out_big', 0)) / 1e4
            small_net = (d.get('capital_in_small', 0) - d.get('capital_out_small', 0)) / 1e4
            main_net = super_net + big_net
            
            flow_tag = ""
            if main_net > 30 and small_net < 0: flow_tag = "🔥機構吸籌"
            elif main_net < -50 and small_net > 0: flow_tag = "⚠️主力派發"
            elif main_net > 10: flow_tag = "🔴主力淨買"
            elif main_net < -10: flow_tag = "🟢主力淨賣"

            return t, {
                "MainNet": main_net, "SuperNet": super_net,
                "FlowTag": flow_tag, "HasFutu": True
            }
    except Exception:
        pass
    return t, {"MainNet": 0.0, "SuperNet": 0.0, "FlowTag": "", "HasFutu": False}

def sync_to_google_sheet(sheet_name, matrix):
    try:
        print(f"\n📡 正在傳送 {len(matrix)} 行數據至 Google 試算表 [{sheet_name}]...")
        payload = {"sheet_name": sheet_name, "data": json.loads(json.dumps(matrix, default=str))}
        res = requests.post(WEBAPP_URL, json=payload, timeout=60)
        print(f"📥 伺服器狀態碼: {res.status_code}")
        if res.status_code == 200:
            print(f"🎉 恭喜！V110 宏觀全景版 已成功同步至 [{sheet_name}]！")
    except Exception as e: 
        print(f"❌ 同步失敗: {e}")

# =====================================================================
# 3. 核心量化模型 V110 (Mag 7 + Macro Assets + Options)
# =====================================================================
def run_master_v110():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = get_universe()
    if "QQQ" not in universe: universe.append("QQQ")
    
    print("\n" + "="*60)
    print(f"⚔️ [大師先勝獵殺量化系統 V110] 啟動 | 股票池總數: {len(universe)}")

    # 1. 抓取宏觀資產 (ES期貨/SPY, QQQ, GLD黃金, USO原油, VIX) 與 七姐妹 (Mag 7)
    print("🌍 正在獲取宏觀資產 (ES, QQQ, GLD, USO, VIX) 與科技七姐妹數據...")
    macro_tickers = ["SPY", "QQQ", "^VIX", "GLD", "USO", "ES=F"] + MAG_7
    try:
        m_hist = yf.download(macro_tickers, period="5d", progress=False)['Close']
        
        # ES 期貨 / SPY 漲跌
        es_series = m_hist['ES=F'].dropna() if 'ES=F' in m_hist and not m_hist['ES=F'].dropna().empty else m_hist['SPY'].dropna()
        es_1d = (es_series.iloc[-1] / es_series.iloc[-2]) - 1 if len(es_series) >= 2 else 0.0
        
        # QQQ, GLD, USO, VIX 漲跌
        qqq_1d = get_ret(m_hist['QQQ'].dropna(), 1)
        gld_1d = get_ret(m_hist['GLD'].dropna(), 1)
        uso_1d = get_ret(m_hist['USO'].dropna(), 1)
        vix_val = float(m_hist['^VIX'].dropna().iloc[-1]) if '^VIX' in m_hist and not m_hist['^VIX'].dropna().empty else 16.0
        
        # 計算七姐妹 (Mag 7) 1D 平均漲幅
        mag7_rets = [get_ret(m_hist[t].dropna(), 1) for t in MAG_7 if t in m_hist and len(m_hist[t].dropna()) >= 2]
        mag7_avg_1d = float(np.mean(mag7_rets)) if mag7_rets else 0.0

        macro_banner = f"ES:{es_1d*100:+.2f}% | QQQ:{qqq_1d*100:+.2f}% | GLD:{gld_1d*100:+.2f}% | USO:{uso_1d*100:+.2f}% | VIX:{vix_val:.1f} | 七姐妹均漲:{mag7_avg_1d*100:+.2f}%"
    except Exception as e:
        macro_banner = "ES:+0.00% | QQQ:+0.00% | GLD:+0.00% | USO:+0.00% | VIX:16.0 | 七姐妹:掃描中"

    # 2. 全市場 2 年歷史 K 線下載
    hist_all = yf.download(universe, period="2y", progress=False, threads=True)
    close_df, vol_df, high_df, low_df = hist_all['Close'], hist_all['Volume'], hist_all['High'], hist_all['Low']
    qqq_c = close_df["QQQ"].dropna() if "QQQ" in close_df.columns else yf.Ticker("QQQ").history(period="2y")['Close']

    # 多週期收益率與 RPS 排名
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

    stock_analysis = {}
    above_50ma = 0
    for t in valid_tickers:
        try:
            c, v, h, l = close_df[t].dropna(), vol_df[t].dropna(), high_df[t].dropna(), low_df[t].dropna()
            if len(c) < 130 or len(v) < 60: continue
            
            p, p_prev = float(c.iloc[-1]), float(c.iloc[-2])
            m50 = float(c.tail(50).mean())
            ema20 = float(c.ewm(span=20, adjust=False).mean().iloc[-1])
            if p > m50: above_50ma += 1
            
            r20, r60, r120 = r20_rank.get(t, 50), r60_rank.get(t, 50), r120_rank.get(t, 50)
            total_rank = round((0.2 * r20) + (0.4 * r60) + (0.4 * r120), 1)

            common_idx = c.index.intersection(qqq_c.index)
            rs_line = c.loc[common_idx] / qqq_c.loc[common_idx]
            rs_ma50 = rs_line.rolling(50).mean()
            rs_above_ma = bool(rs_line.iloc[-1] > rs_ma50.iloc[-1]) if len(rs_ma50.dropna()) > 0 else False
            rs_ma_up = bool(rs_ma50.iloc[-1] > rs_ma50.iloc[-5]) if len(rs_ma50.dropna()) >= 5 else False
            rs_strong = rs_above_ma and rs_ma_up

            cv = c * v
            vwma20 = (cv.rolling(20).sum() / v.rolling(20).sum()).iloc[-1]
            vwma60 = (cv.rolling(60).sum() / v.rolling(60).sum()).iloc[-1]
            p_above_vwma = p > vwma20 and p > vwma60

            black_line = float(c.tail(60).max())
            red_line = float(c.iloc[-11:-1].max())
            is_breakout = p >= black_line * 0.985
            is_red_break = (p > red_line) and (p_prev <= red_line) and (p > vwma20)
            tightness = float((c.tail(15).std() / c.tail(15).mean()) * 100)
            is_vcp = tightness < 3.2

            rsi_val = float(calculate_rsi(c, 14).iloc[-1])
            dist_to_ema20 = ((p - ema20) / ema20) * 100
            vol_ratio = float(v.iloc[-1] / v.tail(20).mean()) if len(v) >= 20 else 1.0
            adr = float(((h - l) / l).tail(20).mean() * 100) if len(l) >= 20 else 2.0
            ytd = float((p / c.loc[c.index <= YTD_BASE_DATE].iloc[-1]) - 1) if not c.loc[c.index <= YTD_BASE_DATE].empty else 0.0

            est_mcap = (p * v.tail(20).mean() * 50) / 1e9 

            spark_data = ",".join([str(round(val, 2)) for val in c.tail(60).tolist()])
            spark_formula = f'=SPARKLINE({{{spark_data}}}, {{"charttype","line";"linewidth",2;"color","blue"}})'

            stock_analysis[t] = {
                "Price": p, "1D": (p/p_prev) - 1, "Trend": spark_formula,
                "20R": r20, "60R": r60, "120R": r120, "TotalRank": total_rank,
                "RSI": rsi_val, "RS_Strong": rs_strong, "VWMA_Up": p_above_vwma,
                "Dist20": dist_to_ema20, "IsBreakout": is_breakout, "IsRedBreak": is_red_break,
                "IsVCP": is_vcp, "Tight": tightness, "VolRatio": vol_ratio,
                "ADR": adr, "YTD": ytd, "EstMCap": est_mcap
            }
        except Exception:
            continue

    infos = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        for t, info in executor.map(fetch_info, list(stock_analysis.keys())):
            if info: infos[t] = info

    pre_candidates = []
    for t, data in stock_analysis.items():
        if t not in infos: continue
        info = infos[t]
        ind = str(info.get('industry') or 'Unknown')
        sec = str(info.get('sector') or 'Unknown')
        mcap_val = info.get('marketCap')
        mcap = (float(mcap_val) / 1e9) if (mcap_val and float(mcap_val) > 0) else data['EstMCap']

        is_master = t in MASTER_CURRENT
        is_mag7 = t in MAG_7
        if not is_master and not is_mag7 and any(ex.lower() in ind.lower() for ex in EXCLUDED): continue

        tr, r20, r60, r120 = data['TotalRank'], data['20R'], data['60R'], data['120R']
        rsi, dist = data['RSI'], data['Dist20']

        is_springboard = (r120 >= 90.0 and r60 >= 85.0 and 20.0 <= r20 <= 60.0 and 42.0 <= rsi <= 62.0 and -3.0 <= dist <= 2.5)
        is_hpe_breakout = (r120 >= 88.0 and r60 >= 88.0 and r20 >= 75.0 and data['IsBreakout'] and data['VolRatio'] > 1.15 and rsi <= 73.0)

        final_score = tr
        if is_springboard: final_score += 8
        if is_hpe_breakout: final_score += 7
        if data['RS_Strong']: final_score += 4
        if data['VWMA_Up']: final_score += 3
        if rsi >= 74: final_score -= 8
        if dist < -8.0: final_score *= 0.5
        if is_master: final_score += 1000
        elif is_mag7: final_score += 500  # 七姐妹權重優先列入觀察

        pre_candidates.append({
            "Ticker": t, "Name": str(info.get('shortName') or info.get('longName') or t)[:16],
            "Industry": ind, "Sector": sec, "MCap": mcap, "Price": data['Price'],
            "1D": data['1D'], "Trend": data['Trend'], "20R": r20, "60R": r60,
            "120R": r120, "TotalRank": tr, "RSI": round(rsi, 1), "ADR": data['ADR'],
            "Vol": data['VolRatio'], "YTD": data['YTD'], "Score": final_score,
            "RS_Status": "🔥向上" if data['RS_Strong'] else "平緩", "Dist20": dist,
            "IsBreakout": data['IsBreakout'], "IsRedBreak": data['IsRedBreak'],
            "IsVCP": data['IsVCP'], "VWMA_Up": data['VWMA_Up'], "RS_Strong": data['RS_Strong'],
            "is_springboard": is_springboard, "is_hpe_breakout": is_hpe_breakout
        })

    pre_candidates.sort(key=lambda x: x['Score'], reverse=True)
    top_pool = pre_candidates[:35]

    # 多線程抓取富途主力籌碼
    futu_flows = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        for t, flow_data in executor.map(fetch_futu_capital_flow, [r['Ticker'] for r in top_pool]):
            futu_flows[t] = flow_data

    final_candidates = []
    for r in top_pool:
        t = r['Ticker']
        is_master = t in MASTER_CURRENT
        is_mag7 = t in MAG_7
        dist = r['Dist20']
        dist_fmt = f"{dist:+.1f}%"
        tr, rsi, p = r['TotalRank'], r['RSI'], r['Price']
        flow_info = futu_flows.get(t, {"MainNet": 0.0, "SuperNet": 0.0, "FlowTag": "", "HasFutu": False})

        tags = []
        if is_mag7: tags.append("👑七姐妹")
        if r['is_springboard']: tags.append("🔥黃金彈簧")
        elif r['is_hpe_breakout']: tags.append("🚀全週期突破")
        elif r['IsBreakout']: tags.append("真空突破")
        elif r['IsRedBreak']: tags.append("紅線突破")
        
        if r['VWMA_Up']: tags.append("籌碼多頭")
        if r['RS_Strong']: tags.append("RS強")
        if flow_info['FlowTag']: tags.append(flow_info['FlowTag'])
        if rsi >= 74: tags.append("⚠️過熱")
        elif 42 <= rsi <= 60: tags.append("買區")
        msg_str = "|".join(tags) if tags else "穩健"

        # 作戰指令
        if is_master:
            if dist < -8.0: action = f"🛡️觸發硬止損({dist_fmt})"
            elif tr < 70 or r['120R'] < 75: action = f"⚠️動量衰竭(換股)({dist_fmt})"
            elif r['is_springboard'] or (-2.5 <= dist <= 2.0 and 42 <= rsi <= 60): action = f"🎯安全加倉({dist_fmt})"
            elif rsi >= 74 or dist > 8.0: action = f"👑過熱持倉({dist_fmt})"
            else: action = f"👑標準持倉({dist_fmt})"
        else:
            if tr < 75 or r['120R'] < 80 or not r['RS_Strong']:
                action = f"⚠️淘汰弱勢({dist_fmt})"
            elif rsi >= 74 or dist > 8.5:
                action = f"👀過熱禁追({dist_fmt})"
            elif r['is_springboard']:
                action = f"🎯彈簧狙擊({dist_fmt})"
            elif r['is_hpe_breakout']:
                action = f"🎯突破狙擊({dist_fmt})"
            elif tr >= 80 and (-2.5 <= dist <= 2.5 and 42 <= rsi <= 60) and (r['IsVCP'] or r['VWMA_Up']):
                action = f"🎯回踩狙擊({dist_fmt})"
            elif tr >= 80 and r['RS_Strong']:
                action = f"🔍強勢觀察({dist_fmt})"
            else:
                action = f"🔍蓄勢待發({dist_fmt})"

        # 期權策略自動推導
        option_strategy = ""
        strike_target = round(p * 1.02, 1)
        if "🎯" in action:
            if r['is_springboard']: option_strategy = f"🔥買45天Call (${strike_target})"
            elif r['is_hpe_breakout']: option_strategy = f"🚀買30天Call (${strike_target})"
            else: option_strategy = f"🎯買60天Call (${strike_target})"
        elif "過熱" in action: option_strategy = f"🛑禁買Call (可平倉止盈)"
        elif "止損" in action or "淘汰" in action: option_strategy = f"❌清倉期權/認賠"
        else: option_strategy = f"👀觀察候選 (暫無合約)"

        main_net_val = flow_info['MainNet']
        super_net_val = flow_info['SuperNet']
        main_net_str = f"{'+' if main_net_val>0 else ''}{round(main_net_val, 1)}萬" if flow_info['HasFutu'] else "-"
        super_net_str = f"{'+' if super_net_val>0 else ''}{round(super_net_val, 1)}萬" if flow_info['HasFutu'] else "-"

        r['Action'] = action
        r['Msg'] = msg_str
        r['OptionStrategy'] = option_strategy
        r['MainNetStr'] = main_net_str
        r['SuperNetStr'] = super_net_str
        final_candidates.append(r)

    top_leaders, sec_count = [], {}
    for r in final_candidates:
        is_master = r['Ticker'] in MASTER_CURRENT
        is_mag7 = r['Ticker'] in MAG_7
        if not is_master and not is_mag7:
            if sec_count.get(r['Sector'], 0) >= 5: continue
            sec_count[r['Sector']] = sec_count.get(r['Sector'], 0) + 1
        top_leaders.append(r)
        if len(top_leaders) >= 30: break

    # 6. 組裝輸出矩陣
    headers = [
        "排名", "代碼", "名稱/行業", "作戰指令(大師先勝)", "🎯期權先勝策略指引", "Msg結構標籤", 
        "Total Rank", "20R(1M)", "60R(3M)", "120R(6M)", "RSI(14)", 
        "RS/QQQ動量", "主力淨流", "超大單", "60日走勢(圖)", "現價", "1D%", "今年YTD", 
        "市值(Bil)", "量比", "ADR%", "風控倉位", "硬止損價(-8%)", "綜合評分", "更新時間"
    ]

    market_breadth = (above_50ma / len(valid_tickers) * 100) if valid_tickers else 0
    title_info = f"⚔️ 宏觀全景獵殺 V110 | {macro_banner} | 50MA寬度:{market_breadth:.1f}% | 嚴守 -8% 止損"
    matrix = [[f"Master Macro & Mag7 V110", f"更新: {update_time}", title_info] + [""] * (len(headers) - 3), headers]

    for i, r in enumerate(top_leaders):
        if r['Ticker'] in MASTER_CURRENT:
            t_disp = f"👑 {r['Ticker']}"
            disp_score = f"{round(r['Score'] - 1000, 1)}"
        elif r['Ticker'] in MAG_7:
            t_disp = f"💎 {r['Ticker']}"
            disp_score = f"{round(r['Score'] - 500, 1)}"
        else:
            t_disp = r['Ticker']
            disp_score = f"{round(r['Score'], 1)}"

        pos_limit = "12.5%" if r['TotalRank'] >= 80 else "8.0%"
        stop_loss_price = f_price(r['Price'] * 0.92)

        matrix.append([
            f"T{i+1}", t_disp, f"{r['Ticker']} | {r['Industry'][:10]}", r['Action'], r['OptionStrategy'], r['Msg'],
            f"{r['TotalRank']}分", f"{r['20R']}", f"{r['60R']}", f"{r['120R']}", f"{r['RSI']}",
            r['RS_Status'], r['MainNetStr'], r['SuperNetStr'], r['Trend'], f_price(r['Price']), f_1d(r['1D']), f_pct(r['YTD']),
            f"${round(r['MCap'], 1)}B", f"{round(r['Vol'], 2)}x", f"{round(r['ADR'], 2)}%",
            pos_limit, f"{stop_loss_price}", disp_score, update_time
        ])

    sync_to_google_sheet(TARGET_SHEET, matrix)

if __name__ == "__main__":
    run_master_v110()
