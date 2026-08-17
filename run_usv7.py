import requests
import json

WEBAPP_URL = "https://script.google.com/macros/s/AKfycbwOeFrqRcFb-MzMYe61qMwV36gqRMlyEmI7Mvjn_FdwsBVmNXL805kr0iT7ySr2G2Db/exec"
TARGET_SHEET = "us Screener"

test_payload = {
    "sheet_name": TARGET_SHEET,
    "data": [
        ["測試欄位1", "測試欄位2", "連線狀態"],
        ["Hello", "Google Sheet", "✅ 成功連線寫入！"]
    ]
}

try:
    res = requests.post(WEBAPP_URL, json=test_payload, timeout=20)
    print("狀態碼:", res.status_code)
    print("伺服器回應:", res.text)
except Exception as e:
    print("連線異常:", e)
