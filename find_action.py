import re
from curl_cffi import requests
from bs4 import BeautifulSoup

def find_action_ids():
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
            # Las Action IDs en JS suelen verse como action=function(){return o("7f22070460c931899c5e38e8e653ffe50af098bc89")}
            # o simplemente ser un hash de 40 chars
            matches = re.findall(r'([a-f0-9]{40})', js_res.text)
            action_ids.update(matches)
        except:
            pass
            
    print(f"Action IDs encontrados: {action_ids}")
    
    # Probar cuál funciona para la paginación
    h_base = {
        'accept': 'text/x-component',
        'content-type': 'text/plain;charset=UTF-8'
    }
    data = '[26,{"mode":"search","filters":{},"search":"$undefined","pagination":{"page":1,"limit":50},"sorting":{"field":"rating","direction":"desc"}}]'
    
    for aid in action_ids:
        h = h_base.copy()
        h['next-action'] = aid
        res_post = requests.post(url, headers=h, data=data, impersonate='chrome120')
        if res_post.status_code == 200 and 'builder_name' in res_post.text:
            print(f"!!! Encontrado Action ID válido: {aid}")
            return aid
            
    print("Ninguno sirvió.")

if __name__ == '__main__':
    find_action_ids()
