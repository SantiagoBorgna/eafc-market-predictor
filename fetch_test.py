import re
from curl_cffi import requests
res = requests.get('https://www.futwiz.com/fc26/players', impersonate='chrome120')

print("Buscando __NEXT_DATA__:")
print("__NEXT_DATA__" in res.text)

print("Buscando Next-Action ID posible:")
matches = re.findall(r'([a-f0-9]{40})', res.text)
if matches:
    print("Action IDs encontrados:", set(matches))
else:
    print("Ningún Action ID de 40 chars hex.")

print("Buscando buildId:")
build_match = re.search(r'"buildId":"([^"]+)"', res.text)
if build_match:
    print("Build ID:", build_match.group(1))
else:
    print("No buildId found.")

print("Buscando nextConfig:")
nextConfig_match = re.search(r'nextConfig.*?(?=\n)', res.text)
if nextConfig_match:
    print(nextConfig_match.group(0)[:100])
