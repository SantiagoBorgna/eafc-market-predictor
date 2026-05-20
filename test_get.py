import re
from curl_cffi import requests
res = requests.get('https://www.futwiz.com/fc26/players?page=2', impersonate='chrome120')
match = re.search(r'\[\{.*?"builder_name".*?\}\]', res.text)
print("Blob found:", match is not None)
if match:
    print(match.group(0)[:200])
