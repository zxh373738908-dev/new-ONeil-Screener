import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import requests
import json
import warnings
import math
import time

warnings.filterwarnings('ignore')

# ==========================================
# 1. 戰略配置中心
# ==========================================
WEBAPP_URL = "https://script.google.com/macros/s/AKfycbw_f6Uy1OMIIl-4mLsAaxe1rXr64qYf2j0RHoKl3-xu0QOp-5kqFpk9rTBIV9Yf5-kz/exec" 

# 核心戰略池 (精選各賽道最強龍頭 - 這裡是您的底氣，只打富裕仗)
CORE_UNIVERSE = [
    "600519", "601318", "000858", "600036", "600900", "000333", "601012", "300750", 
    "300760", "600276", "601888", "002594", "002475", "603259", "002714", "601899", 
    "603288", "600585", "600309", "002415", "600104", "002352", "000001", "600887", 
    "600690", "000651", "000725", "601668", "300059", "300413", "300124", "600438",
    "601138", "603501", "688041", "300308" # 補充幾支科技/算力龍頭
]

# ==========================================
# 2. 基礎工具函數
# ==========================================
def sync_to_google_sheet(sheet_name, matrix):
    try:
        def safe_json_val(val):
            if isinstance(val, float) and not math.isfinite(val): return 0
            return str(val)
        payload = {"sheet_name": sheet_name, "data": json.loads(json.dumps(matrix, default=safe_json_val))}
        r = requests.post(WEBAPP_URL, json=payload, timeout=30)
        print(f"✅ 戰報已送達指揮部 | 響應: {r.text}")
    except Exception as e: 
        print(f"❌ 通訊中斷: {e}")

def format_a_tickers(ticker_list):
    formatted = []
    for t in ticker_list:
        t_str = str(t).strip().zfill(6)
        display_code = f"'{t_str}" 
        yf_code = f"{t_str}.SS" if t_str.startswith(('6', '9')) else f"{t_str}.SZ"
        formatted.append((display_code, yf_code))
    return list(set(formatted))

# ==========================================
# 3. 🚀 終極先勝後戰 引擎核心
# ==========================================
def main():
    print("\n" + "⚔️"*20)
    print("🔥 [先勝後戰 V90.0 終極狙擊版] 啟動...")
    print("⚔️"*20)
    
    ticker_pairs = format_a_tickers(CORE_UNIVERSE)
    yf_codes = [p[1] for p in ticker_pairs]
    
    print(f"📡 正在獲取 {len(yf_codes)} 隻戰略龍頭的 K線與籌碼數據...")
    # 一次性併發下載，速度極快，不需要 yf.info
    data = yf.download(yf_codes, period="1y", progress=False, group_by='ticker', threads=True)
    
    candidates = []
    
    # 步驟 1: 基礎數據計算
    for display_t, yf_t in ticker_pairs:
        try:
            df = data[yf_t].dropna()
            if len(df) < 130: continue
            
            c, v, h, l = df['Close'], df['Volume'], df['High'], df['Low']
            curr_p = float(c.iloc[-1])
            prev_p = float(c.iloc[-2])
            
            # --- 【兵法1：籌碼成本線 VWAP】(融合代碼A) ---
            vwma_120 = (c * v).tail(120).sum() / v.tail(120).sum() # 戰略無窮成本線
            vwma_20 = (c * v).tail(20).sum() / v.tail(20).sum()    # 戰術機構建倉線
            
            # --- 【兵法2：動能與 RPS 基礎】(融合代碼C) ---
            ret_20 = (curr_p / c.iloc[-21]) - 1
            ret_120 = (curr_p / c.iloc[-121]) - 1
            combined_ret = ret_20 * 0.4 + ret_120 * 0.6 # 長短動能加權
            
            # --- 【兵法3：VCP 波動收縮與量能】(深度升級) ---
            tightness = (c.tail(15).std() / c.tail(15).mean()) * 100 # 近15天價格波動率
            vol_ratio = v.iloc[-1] / v.tail(10).mean() # 今日量比
            
            # 乖離率 (距離 20日機構成本的距離)
            bias_vwma20 = ((curr_p - vwma_20) / vwma_20) * 100
            
            # 繪製 60日微型趨勢圖
            prices_str = ",".join([str(round(p, 2)) for p in c.tail(60).tolist()])
            line_color = "#00b050" if curr_p >= c.iloc[-60] else "#ff0000"
            sparkline = f'=SPARKLINE({{{prices_str}}}, {{"charttype","line";"color","{line_color}"}})'

            candidates.append({
                "T": display_t, "P": curr_p, "Raw_Ret": combined_ret,
                "1D": (curr_p/prev_p-1)*100,
                "VWMA_120": vwma_120, "VWMA_20": vwma_20,
                "Bias": bias_vwma20,
                "Tight": tightness, "VolRatio": vol_ratio,
                "Trend": sparkline
            })
        except Exception as e: 
            continue

    if not candidates: 
        print("❌ 沒有獲取到有效數據")
        return
    
    # 步驟 2: 計算 RPS 排名 (龍頭池內的相對強度)
    all_rets = [x['Raw_Ret'] for x in candidates]
    for c in candidates:
        c['RPS_Rank'] = sum(1 for r in all_rets if r <= c['Raw_Ret']) / len(all_rets) * 100

    # 步驟 3: 【先勝後戰】戰術信號引擎
    final_results = []
    for c in candidates:
        # 大前提：必須在 120 日長期成本線之上 (不立危牆之下)
        is_bull = c['P'] > c['VWMA_120']
        
        # 戰術判定
        if is_bull:
            # 💡 完美狙擊 (先勝之境)：貼近主力成本 + 波動極度收縮 + 量能萎縮
            if abs(c['Bias']) <= 2.5 and c['Tight'] < 2.5 and c['VolRatio'] < 0.8:
                action = "🎯 完美伏擊 (必殺)"
                score_bonus = 30
            # 🚀 突破強攻：帶量突破機構成本線
            elif c['1D'] > 2.5 and c['VolRatio'] > 1.5 and c['P'] > c['VWMA_20']:
                action = "🚀 放量強攻 (追擊)"
                score_bonus = 15
            # ⚠️ 乖離過大：主力賺太多了，隨時砸盤
            elif c['Bias'] > 12:
                action = "⚠️ 乖離過大 (禁追)"
                score_bonus = -20
            else:
                action = "🛡️ 均線上持倉"
                score_bonus = 0
        else:
            action = "⚪ 弱勢觀望"
            score_bonus = -50
            
        # 最終綜合戰鬥力得分 = RPS強度 + 戰術加分
        c['Final_Score'] = min(100, max(0, c['RPS_Rank'] * 0.7 + score_bonus))
        c['Action'] = action
        final_results.append(c)

    # 排序：優先展示得分最高、最具狙擊價值的標的
    final_results = sorted(final_results, key=lambda x: x['Final_Score'], reverse=True)
    
    # 步驟 4: 組裝報表並推流
    rows = []
    for r in final_results[:20]: # 輸出前 20 名
        rows.append([
            r['Action'],            # 戰術指令放第一列，一目了然
            r['T'],                 # 代碼
            f"{r['Final_Score']:.0f}", # 綜合勝率分
            f"{r['1D']:+.2f}%",     # 1日漲幅
            r['Trend'],             # 60日趨勢圖
            f"{r['RPS_Rank']:.0f}", # RPS 排名
            f"{r['Bias']:+.2f}%",   # 距離 20日機構成本的距離 (極其重要)
            f"{r['Tight']:.1f}%",   # VCP 緊湊度 (越小越好)
            f"{r['VolRatio']:.2f}", # 量比
            round(r['P'], 2)        # 現價
        ])

    tz = datetime.timezone(datetime.timedelta(hours=8))
    h1 = ["🏰 先勝後戰 終極融合 V90.0", "更新:", datetime.datetime.now(tz).strftime('%m-%d %H:%M'), "核心:", "VWAP成本 + VCP收縮 + RPS強度", "", "", "", "", ""]
    h2 = ["作戰指令", "代碼", "勝率分", "1D%", "近60日趨勢", "RPS排名", "主力成本乖離", "VCP波動率", "今日量比", "現價"]
    
    # 注意修改你在 GAS 中的 sheet_name
    sync_to_google_sheet("A股_先勝後戰", [h1, h2] + rows)

if __name__ == "__main__":
    main()
