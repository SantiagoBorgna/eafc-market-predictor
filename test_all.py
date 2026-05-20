from curl_cffi import requests

action_ids = ['40a60c7bedc6a0b079494005af8182899db1fb98', '7f860a8c4222fc914e9616d38c1a4382ab6863eb', '00584582cf6bb15921062171868ccadc0113f5ac', '7f8a8ed43601a3dfaed0d46168eff8cd88e1d67b', '7f116e808f3f301a0eee2c99150983c27354cf8c', '7f9150570c5f4c3a6f1af3ad587b8125f8a53d09', '7fd2a0e27175d259f067a557bc29d4df1086e7f9', '7fc033d2777f5ec9cc161d7169686b658c9980da', '40ffd17cdd3df69c2fc0e0522a386da890d244d5', '7059549acdf2d8890f831b3bb4923adc2080918b', '00930dddb8d269828a9d0fa6e09f7b8c27a97332']

url = 'https://www.futwiz.com/fc26/players'
h_base = {
    'accept': 'text/x-component',
    'content-type': 'text/plain;charset=UTF-8'
}
data = '[26,{"mode":"search","filters":{},"search":"$undefined","pagination":{"page":1,"limit":50},"sorting":{"field":"rating","direction":"desc"}}]'

for aid in action_ids:
    h = h_base.copy()
    h['next-action'] = aid
    res = requests.post(url, headers=h, data=data, impersonate='chrome120')
    print(f"Action: {aid[:8]} -> Status: {res.status_code}")
    if res.status_code == 500:
        print("  Error 500 payload:", res.text[:200])
    elif res.status_code == 200:
        print("  Success payload:", res.text[:200])
