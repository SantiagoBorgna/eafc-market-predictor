import requests
from bs4 import BeautifulSoup
import time

session = requests.Session()

headers = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.futbin.com/"
}

session.headers.update(headers)

url = "https://www.futbin.com/26/player/40/kylian-mbappe"

# 1️⃣ visitar la página primero
page = session.get(url)

soup = BeautifulSoup(page.text, "html.parser")
nombre = soup.find("h1").text.split("-")[0].strip()

# pequeño delay para evitar bloqueo
time.sleep(2)

# 2️⃣ pedir el precio
player_id = url.split("/player/")[1].split("/")[0]
price_url = f"https://www.futbin.com/playerPrices?player={player_id}"

price_response = session.get(price_url)

if "application/json" not in price_response.headers.get("content-type",""):
    print("FutBin devolvió HTML en vez de JSON (bloqueo)")
else:
    data = price_response.json()
    price = data[player_id]["prices"]["ps"]["LCPrice"]
    print(f"Jugador: {nombre}")
    print(f"Precio: {price}")