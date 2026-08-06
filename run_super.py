import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import requests
import json
import warnings
import math
import urllib.request
import time
import random
from concurrent.futures import ThreadPoolExecutor

warnings.filterwarnings('ignore')

# ==========================================
# 1. 系統配置中心
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycby1pIM7iO43lcLQpOmi5LCJIn3VN9a0Ilf9amoy1EtQV_GBXJkk_A4PpsrJxKzH7i51/exec"
TARGET_SHEET = "super"
YTD_BASE_DATE = "2025-12-31"

# 💡 V100 里程碑：科技股全面回歸！神預言 HPE 入陣，AMD 重磅回歸
MASTER_CURRENT = ["AMD", "ARW", "ATI", "FTNT", "HPE", "HST", "STT", "VIK", "VSAT"]

def get_universe():
    # 將上一波汰換的股票放入備選池，持續追蹤動能
    core_watchlist = MASTER_CURRENT + ["JBHT", "PRM", "ROIV", "ROKU", "TRGP", "YOU", "DAL", "GEV", "IBKR", "LLY", "MNST", "RDDT", "MU", "PWR", "IRDM", "QS", "VRT", "FSLR", "SNDK"]
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', headers=headers, timeout=15)
        sp500 = pd.read_html(res.text)[0]['Symbol'].tolist()
        return list(set([t.replace('.', '-') for t in sp500] + core_watchlist))
    except: return core_watchlist

EXCLUDED = ['Commercial Banks', 'Savings Institutions', 'Mortgage', 'Real Estate']

# ==========================================
# 2. 數據獲取與處理
# ==========================================
def fetch_info_v100(t):
    ticker = yf.Ticker(t)
    try:
        time.sleep(random.uniform(0.1, 0.3))
        info = ticker.info
        if info and 'industry' in info:
            info['industry'] = str(info['industry']).strip().replace('\t', '')
            return t, info
    except: pass
    try:
        fast = ticker.fast_info
        return t, {'industry': 'Growth/Service', 'sector': 'Technology', 'marketCap': fast.market_cap, 'revenueGrowth': 0.1}
    except: return t, {}

def sync_to_google_sheet(sheet_name, matrix):
    try:
        payload = {"sheet_name": sheet_name, "data": json.loads(json.dumps(matrix, default=str))}
        requests.post(WEBAPP_URL, json=payload, timeout=50)
        print(f"🎉 V100 科技復甦與里程碑版 同步完成！大師的底牌已鎖定。")
    except Exception as e: print(f"❌ 同步失敗: {e}")

def get_ret(series, days):
    if series is None or len(series) < days + 1: return 0.0
    return (series.iloc[-1] / series.iloc[-(days+1)]) - 1

def f_pct(v): return f"{round(v*100, 2)}%" if not pd.isna(v) else "0.00%"
def f_price(v): return f"${round(v, 2)}" if not pd.isna(v) else "$0.00"
def f_1d(v): return f"{v*100:+.2f}%" if not pd.isna(v) else "+0.00%"

# ==========================================
# 3. 核心量化模型 V100 (Tech Resurgence)
# ==========================================
def run_super_growth_v100():
    update_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    universe = get_universe()
    
    print("\n" + "="*50)
    print(f"🚀 [超級成長股 V100] 啟動 | 神預言 HPE 命中，科技板塊全面接管...")

    # 1. 宏觀數據
    try:
        m_data = yf.download(["SPY", "^VIX", "BNO", "GLD", "CPER"], period="2y", progress=False)['Close']
        spy_hist = m_data['SPY'].dropna()
        vix_val = float(m_data['^VIX'].dropna().iloc[-1])
        if vix_val < 0.1: vix_val = float(yf.Ticker("^VIX").history(period="5d")['Close'].iloc[-1])
        
        spy_r = {20: get_ret(spy_hist, 20), 60: get_ret(spy_hist, 60), 120: get_ret(spy_hist, 120)}
        curr_spy, ma50_spy = float(spy_hist.iloc[-1]), float(spy_hist.tail(50).mean())
        
        weather = "☀️ 科技復甦" if curr_spy > ma50_spy and vix_val < 22 else ("☁️ 震盪洗盤" if curr_spy > ma50_spy else "📉 跌破趨勢")
        strategy = "🚀 滿血進攻：擁抱半導體與高 Alpha 科技股" if vix_val < 20 else "⚠️ 提高警覺，緊盯停損"
        
        bno_val = float(m_data['BNO'].dropna().iloc[-1])
        cper_val = float(m_data['CPER'].dropna().iloc[-1])
        gld_val = float(m_data['GLD'].dropna().iloc[-1])
        macro_text = f"BNO:${bno_val:.1f} | 銅金比:{cper_val/gld_val:.3f}"
    except Exception as e: 
        print(f"⚠️ 宏觀數據獲取異常: {e}")
        weather, vix_val, spy_r, strategy, macro_text = "❓", 19.0, {20:0,60:0,120:0}, "數據同步", "掃描中"

    # 2. 技術面深度掃描
    hist_all = yf.download(universe, period="2y", progress=False, threads=True)
    close_df = hist_all['Close']

    tech_results, above_50ma, perfect_tickers = {}, 0, []
    for t in universe:
        try:
            if t not in close_df.columns: continue
            c = close_df[t].dropna()
            if len(c) < 150: continue 
            
            p = float(c.iloc[-1])
            m20, m50, m200 = c.tail(20).mean(), c
