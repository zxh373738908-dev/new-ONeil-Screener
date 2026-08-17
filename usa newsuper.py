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
WEBAPP_URL = "https://script.google.com/macros/s/AKfycbxuM4xO0WAPnBPNMcCSlvnzAUmLJYgUr3EHc5qg2gw4vxB9D6F7DODn7ymq-VQa4TIo/exec"
TARGET_SHEET = "usa newsuper"
YTD_BASE_DATE = "2025-12-31"

# 💡 V102: 保持科技股滿血陣容
MASTER_CURRENT = ["AMD", "ARW", "ATI", "FTNT", "HPE", "HST", "STT", "VIK", "VSAT"]

def get_universe():
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
def fetch_info_v102(t):
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
        res = requests.post(WEBAPP_URL, json=payload, timeout=50)
        if res.status_code == 200:
            print(f"🎉 V102 雙線狙擊版 同步完成！已成功寫入工作表 [{sheet_name}]。")
        else:
            print(f"⚠️ 伺服器回應狀態碼: {res.status_code}, 內容: {res.text}")
    except Exception as e: 
        print(f"❌ 同步失敗: {e}")

def get_ret(series, days):
    if series is None or len(series) < days + 1: return 0.0
    return (series.iloc[-1] / series.iloc[-(days+1)]) - 1

def f_pct(v): return f"{round(v*100, 2)}%" if not pd.isna(v) else "0.00%"
def f_price(v): return f"${round(v, 2)}" if not pd.isna(v) else "$0.00"
def f_1d(v): return f"{v*100:+.2f}%"
