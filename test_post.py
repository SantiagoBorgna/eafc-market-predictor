from curl_cffi import requests
url = 'https://www.futwiz.com/fc26/players'
h = {
    'next-action': '833ccba57c9e4d2798f2e76cebdd09a117781722',
    'accept': 'text/x-component',
    'content-type': 'text/plain;charset=UTF-8'
}
data = '[26,{"mode":"search","filters":{},"search":"$undefined","pagination":{"page":1,"limit":50},"sorting":{"field":"rating","direction":"desc"}}]'
res = requests.post(url, headers=h, data=data, impersonate='chrome120')
print("Status:", res.status_code)
print("Response preview:", res.text[:200])
