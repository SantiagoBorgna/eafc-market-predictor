from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

def test_pw():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://www.futwiz.com/fc26/players?page=2", wait_until="networkidle")
        html = page.content()
        
        soup = BeautifulSoup(html, 'html.parser')
        # Check how many players
        players = soup.select('.player')
        print(f"Players found: {len(players)}")
        
        # If any, try to print the first one's name and price
        if players:
            name = players[0].select_one('.name').text if players[0].select_one('.name') else 'No name'
            price = players[0].select_one('.fc25-card__price-value')
            print(f"Player 1: {name} - Price: {price.text if price else 'No price'}")
            
        browser.close()

if __name__ == "__main__":
    test_pw()
