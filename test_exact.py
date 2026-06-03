from curl_cffi import requests
url = 'https://www.futwiz.com/fc26/players'
h = {
    'next-action': '7f9150570c5f4c3a6f1af3ad587b8125f8a53d0927',
    'accept': 'text/x-component',
    'content-type': 'text/plain;charset=UTF-8'
}
data = '[26,{"mode":"search","filters":{},"search":"$undefined","pagination":{"page":1,"limit":40},"sorting":{"field":"rating","direction":"desc"}}]'
res = requests.post(url, headers=h, data=data, impersonate='chrome120')
print("Status:", res.status_code)
if res.status_code == 200:
    print("Success:", res.text[:100])
