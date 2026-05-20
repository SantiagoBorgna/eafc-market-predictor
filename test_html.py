from bs4 import BeautifulSoup
import json
import re

with open('page2.html', 'r', encoding='utf-8') as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')

# In App Router, the data might be injected as inline JSON in <script> tags for React Server Components
rsc_scripts = soup.find_all('script')
for s in rsc_scripts:
    if s.string and 'builder_name' in s.string:
        print("Found builder_name in script")
        print(s.string[:200])

# Let's see if there are any HTML elements holding the data
players = soup.find_all(lambda tag: tag.has_attr('data-player-id') or tag.has_attr('data-id'))
print("Players found:", len(players))

# Print snippet of HTML where "prices" is
idx = html.find('prices')
if idx != -1:
    print("Contexto de 'prices':")
    print(html[max(0, idx-100):idx+500])
