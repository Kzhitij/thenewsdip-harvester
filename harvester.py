import os  # Add this to your imports at the top
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from collections import Counter, defaultdict
import urllib.parse
import feedparser  # <--- THIS IS THE MISSING PIECE
import json
import requests
import spacy
import hashlib
from bs4 import BeautifulSoup

# Load lightweight NLP model for Entity Extraction
nlp = spacy.load("en_core_web_sm")

# Sample RSS Feeds (You can add global, national, and regional feeds here)
FEEDS = [
    "https://news.google.com/rss/search?q=latest&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/sections/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0ZqcEJVaTloV0Vnd09BTVM_hl=en-IN&gl=IN&ceid=IN:en"
]

def generate_hashtag_variants(topic):
    """Generates intelligent hashtag variants based on the core topic."""
    words = topic.split()
    base_tag = "".join(word.capitalize() for word in words)
    return [
        f"{base_tag}",
        f"{base_tag}News",
        f"{base_tag}Update",
        f"{words[0].capitalize()}Economy" if len(words) > 1 else f"{base_tag}Trend"
    ]

def farm_intelligence_tree(query):
    print(f"[*] Initiating Hashtag Farming for: {query}")
    
    # URL Encode the query for Google News RSS (Targeted for Indian macro updates)
    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
    
    # Fetch and parse the live RSS feed
    feed = feedparser.parse(rss_url)
    
    if not feed.entries:
        print("[-] No live data found on Google Edge nodes.")
        return None

    # 1. Scavenge and Deduplicate Links
    unique_articles = {}
    for entry in feed.entries[:15]: # Scavenge top 15 sources
        # Create a unique hash of the title to strictly prevent duplicate identical articles
        article_hash = hashlib.md5(entry.title.encode('utf-8')).hexdigest()
        
        if article_hash not in unique_articles:
            unique_articles[article_hash] = {
                "title": entry.title,
                "url": entry.link,
                "source": entry.source.title if hasattr(entry, 'source') else "Web",
                "published": entry.published if hasattr(entry, 'published') else "Recent"
            }

    final_links = list(unique_articles.values())
    total_unique = len(final_links)
    
    # 2. Source Diversity Calculation
    unique_publishers = set([link["source"] for link in final_links])
    diversity_percentage = int((len(unique_publishers) / total_unique) * 100) if total_unique > 0 else 0

    # 3. Build the Hashtag Matrix
    hashtag_variants = generate_hashtag_variants(query)
    hashtag_nodes = []
    
    for tag in hashtag_variants:
        quality_score = (diversity_percentage * 0.6) + (total_unique * 4)
        
        hashtag_nodes.append({
            "name": tag,
            "unique_links_count": total_unique,
            "diversity_score": diversity_percentage,
            "quality_score": round(quality_score, 1),
            "links": final_links[:5] # Attach top 5 deepest links directly to the tag
        })

    # Assemble the final JSON payload struct expected by the Chrome Extension
    intelligence_node = {
        "topic": query,
        "summary": f"Aggregated {total_unique} unique perspectives across {len(unique_publishers)} distinct publishers.",
        "hashtags": hashtag_nodes
    }
    
    return intelligence_node

def push_tree_to_live_worker(tree_data):
    worker_url = "https://thenewsdip-backend.thenewsdip.workers.dev/api/update"
    
    # Securely pulls the secret from GitHub's hidden environment variables
    secret_key = os.environ.get("API_SECRET_KEY") 
    
    # Fallback for local testing if the environment variable isn't set on your desktop
    if not secret_key:
        print("⚠ API_SECRET_KEY missing from environment. Using local testing override...")
        secret_key = "MySuperSecretDipEngineToken123!" # Replace with your actual key if testing locally
        
    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json"
    }
    
    payload = json.dumps(tree_data)
    
    print(f"[*] Pushing data tree to edge network at {worker_url}...")
    try:
        response = requests.put(worker_url, headers=headers, data=payload, timeout=15)
        if response.status_code == 200:
            print("✓ Live platform successfully updated and synchronized globally.")
        else:
            print(f"✗ Synch failed with code {response.status_code}: {response.text}")
    except Exception as e:
        print(f"✗ Connection error linking to Cloudflare Platform: {e}")

# --- EXECUTION BLOCK ---
if __name__ == "__main__":
    print("Harvesting and structural tokenization processing initiated...")
    
    # You can add multiple topics to this list to farm several trends at once
    targets = ["RBI Rate Cut", "NSE F&O Regulations"]
    
    final_payload = []
    
    for target in targets:
        farmed_data = farm_intelligence_tree(target)
        if farmed_data:
            final_payload.append(farmed_data)
            print(f"✓ Successfully farmed intelligence tree for '{target}'. Diversity Score: {farmed_data['hashtags'][0]['diversity_score']}%")

    if final_payload:
        # Pushes the complete array to Cloudflare
        push_tree_to_live_worker(final_payload)
    else:
        print("[-] No data farmed. Sync aborted.")
