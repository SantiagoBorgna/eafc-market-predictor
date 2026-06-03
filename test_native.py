import re
from curl_cffi import requests
from bs4 import BeautifulSoup

def resolver_payload_nativo():
    url = 'https://www.futwiz.com/fc26/players'
    res = requests.get(url, impersonate='chrome120')
    soup = BeautifulSoup(res.text, 'html.parser')
    
    scripts = soup.find_all('script', src=True)
    chunks = [s['src'] for s in scripts if '_next/static/chunks' in s['src']]
    
    action_ids = set()
    for chunk in chunks:
        chunk_url = f"https://www.futwiz.com{chunk}" if chunk.startswith('/') else chunk
        try:
            js_res = requests.get(chunk_url, impersonate='chrome120')
            matches = re.findall(r'([a-f0-9]{40,})', js_res.text)
            action_ids.update(matches)
        except:
            continue
            
    # Probar cuál funciona
    h_base = {
        'accept': 'text/x-component',
        'content-type': 'text/plain;charset=UTF-8'
    }
    data = '[26,{"mode":"search","filters":{},"search":"$undefined","pagination":{"page":1,"limit":40},"sorting":{"field":"rating","direction":"desc"}}]'
    
    for aid in action_ids:
        h = h_base.copy()
        h['next-action'] = aid
        try:
            res_post = requests.post(url, headers=h, data=data, impersonate='chrome120', timeout=5)
            if res_post.status_code == 200 and 'builder_name' in res_post.text:
                return {"action_id": aid, "payload": data}
        except:
            pass
            
    return {"action_id": None, "payload": None}

if __name__ == '__main__':
    print(resolver_payload_nativo())
