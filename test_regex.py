import re

with open('page2.html', 'r', encoding='utf-8') as f:
    html = f.read()

print("Prices in HTML:", "prices" in html)

# Try to find the Next.js payload inside <script>
matches = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
for m in matches:
    if "builder_name" in m:
        print("Encontrado builder_name en script:", m[:100])
        
# Match the blob:
blob_match = re.search(r'\[\{.*?"builder_name".*?\}\]', html)
print("Blob found:", blob_match is not None)
if blob_match:
    print(blob_match.group(0)[:200])
