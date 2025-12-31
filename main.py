import os, random, time, datetime, threading, json
from flask import Flask
from playwright.sync_api import sync_playwright
import google.generativeai as genai

# --- 1. CLOUD SERVER SETUP (To prevent Render sleeping) ---
app = Flask('')
@app.route('/')
def home(): return "Bot Active. Monitoring Whales..."

# --- 2. AI CONFIGURATION ---
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
ai_model = genai.GenerativeModel('gemini-1.5-flash')

# --- 3. BOT SETTINGS ---
KEYWORDS = ["#Bitcoin", "AI Tech", "Stock Market", "Passive Income"]
WHALES = ["elonmusk", "MrBeast", "realDonaldTrump", "VitalikButerin", "sama"] # Add all 30 here
replied_tweets = {}

def get_ai_reply(text):
    prompt = f"Write a witty, human-like, 1-sentence reply to this: '{text[:400]}'. No emojis."
    try:
        response = ai_model.generate_content(prompt)
        return response.text.strip()
    except:
        return "Actually a very interesting perspective on this."

def execute_5_actions(tweet, page):
    """Actions: Like, Repost, Reply, Follow, Log"""
    try:
        tweet.locator('div[data-testid="like"]').click()
        time.sleep(1)
        tweet.locator('div[data-testid="retweet"]').click()
        page.locator('div[data-testid="retweetConfirm"]').click()
        
        reply_text = get_ai_reply(tweet.inner_text())
        tweet.locator('div[data-testid="reply"]').click()
        page.wait_for_selector('div[data-testid="tweetTextarea_0"]')
        page.fill('div[data-testid="tweetTextarea_0"]', reply_text)
        page.click('div[data-testid="tweetButtonInline"]')
        
        try:
            tweet.locator('div[data-testid="User-Name"]').hover()
            time.sleep(2)
            page.get_by_role("button", name="Follow").click(timeout=2000)
        except: pass
        print(f"5 Actions complete on new tweet.")
    except Exception as e:
        print(f"Action failed: {e}")

def monitor_logic():
    cookie_json = os.getenv("X_COOKIE_JSON")
    with open("/tmp/state.json", "w") as f:
        f.write(cookie_json)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state="/tmp/state.json")
        page = context.new_page()

        while True:
            try:
                # MODE 1: WHALE MONITORING
                creator = random.choice(WHALES)
                page.goto(f"https://x.com/{creator}")
                page.wait_for_selector('article[data-testid="tweet"]', timeout=10000)
                
                tweet = page.locator('article[data-testid="tweet"]').first
                tid = tweet.get_attribute("id")
                
                if tid and tid != replied_tweets.get(creator):
                    if creator in replied_tweets: # Don't reply on first run
                        execute_5_actions(tweet, page)
                    replied_tweets[creator] = tid
                
                # MODE 2: SEARCH MODE
                page.goto(f"https://x.com/search?q={random.choice(KEYWORDS)}&f=live")
                time.sleep(5)
                # Apply actions to the freshest trending search result
                execute_5_actions(page.locator('article[data-testid="tweet"]').first, page)

                time.sleep(random.randint(600, 1200)) # Sleep 10-20 mins
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(60)

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=10000)).start()
    monitor_logic()
