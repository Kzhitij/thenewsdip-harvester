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
import re
from bs4 import BeautifulSoup

# Load lightweight NLP model for Entity Extraction
nlp = spacy.load("en_core_web_sm")

# Sample RSS Feeds (You can add global, national, and regional feeds here)
FEEDS = [
    "https://news.google.com/rss/search?q=latest&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/sections/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0ZqcEJVaTloV0Vnd09BTVM_hl=en-IN&gl=IN&ceid=IN:en"
]

def resolve_target_url(google_url):
    """Unfurls the Google News tracking link to extract the clean, direct publisher URL."""
    try:
        # We use a standard browser User-Agent so Google doesn't block the extraction
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(google_url, headers=headers, timeout=8, allow_redirects=True)
        
        final_url = response.url
        
        # If Google intercepts with a meta-refresh page, extract the hidden URL manually
        if "news.google.com" in final_url:
            match = re.search(r'URL=\'([^\']+)\'', response.text, re.IGNORECASE)
            if match:
                return match.group(1)
            
            # Secondary check for a hidden data attribute
            match_two = re.search(r'data-n-v="([^"]+)"', response.text)
            if match_two:
                return match_two.group(1)
                
        return final_url
    except Exception:
        # Safe fallback if the unfurl fails
        return google_url

def generate_hashtag_variants(topic):
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
    
    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
    
    feed = feedparser.parse(rss_url)
    
    if not feed.entries:
        print("[-] No live data found on Google Edge nodes.")
        return None

    # 1. Scavenge and Deduplicate Links
    unique_articles = {}
    print(f"[*] Unfurling direct publisher links for '{query}'...")
    
    for entry in feed.entries[:15]: 
        article_hash = hashlib.md5(entry.title.encode('utf-8')).hexdigest()
        
        if article_hash not in unique_articles:
            # Extract the clean destination URL bypassing the Google proxy
            clean_url = resolve_target_url(entry.link)
            
            unique_articles[article_hash] = {
                "title": entry.title,
                "url": clean_url,
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
            "links": final_links[:5] 
        })

    intelligence_node = {
        "topic": query,
        "summary": f"Aggregated {total_unique} unique perspectives across {len(unique_publishers)} distinct publishers.",
        "hashtags": hashtag_nodes
    }
    
    return intelligence_node

def push_tree_to_live_worker(tree_data):
    worker_url = "https://thenewsdip-backend.thenewsdip.workers.dev/api/update"
    secret_key = os.environ.get("API_SECRET_KEY") 
    
    if not secret_key:
        print("⚠ API_SECRET_KEY missing from environment. Using local testing override...")
        secret_key = "MySuperSecretDipEngineToken123!" 
        
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

if __name__ == "__main__":
    print("Harvesting and structural tokenization processing initiated...")
    
    targets = ["RBI Rate Cut", "NSE F&O Regulations"]
    final_payload = []
    
    for target in targets:
        farmed_data = farm_intelligence_tree(target)
        if farmed_data:
            final_payload.append(farmed_data)
            print(f"✓ Successfully farmed intelligence tree for '{target}'. Diversity Score: {farmed_data['hashtags'][0]['diversity_score']}%")

    if final_payload:
        push_tree_to_live_worker(final_payload)
    else:
        print("[-] No data farmed. Sync aborted.")
