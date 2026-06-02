import requests
import json

url = "https://bengalurumeghasandesha.in:93/FloodForecastService.svc/Get_T_DataN"

headers = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://bengalurumeghasandesha.in:93/city.htm?dtcode=01"
}

payload = {
    "t_code": "01",
    "t_type": ""
}

res = requests.post(url, json=payload, headers=headers)

print(res.status_code)
print(res.text[:500])  # preview

data = res.json()

data = res.json()
print(data)
parsed = data["Get_T_DataNResult"][0]["GetTRGDataN"]

for ward in parsed:
    print(ward)


