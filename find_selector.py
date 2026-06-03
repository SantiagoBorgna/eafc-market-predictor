import re
html = open('futwiz2.html', encoding='utf-8').read()
matches = re.findall(r'<a[^>]*class="[^"]*page-link[^"]*"[^>]*>.*?</a>', html)
print("Page link matches:", len(matches))
if matches:
    print(matches[0][:150])

print("Search button?")
button = re.search(r'<button[^>]*>.*?Search.*?</button>', html, re.IGNORECASE)
if button:
    print(button.group(0))
