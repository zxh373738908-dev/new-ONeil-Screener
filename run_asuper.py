import requests

# 這是您剛剛發布的新 Web App URL
url = "https://script.google.com/macros/s/AKfycbz-sv8TCkC9lDMKvBInu6KGeS0P-OOxnlOLNkC-f3p6iHwIDGFBiDC6sN-eZZR_Nm3c/exec"

payload = {
    "sheet_name": "A_Super",
    "data": [["測試欄位1", "測試欄位2"], ["連線成功！", "數據已寫入"]]
}

res = requests.post(url, json=payload)
print("狀態碼:", res.status_code)
print("後台真實回傳內容:", res.text)
