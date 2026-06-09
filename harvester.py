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

def resolve_target_url(google_rss_url):
    """Unfurls the Google tracking link to get the final publisher destination."""
    try:
        response = requests.get(google_rss_url, timeout=5, headers={'User-Agent': 'Mozilla/5.0'})
        return response.url
    except Exception:
        return google_rss_url

def extract_thumbnail_from_rss(description_html):
    """Scavenges for the hidden thumbnail image inside the RSS description."""
    if not description_html: return ""
    try:
        soup = BeautifulSoup(description_html, 'html.parser')
        img = soup.find('img')
        return img['src'] if img and img.get('src') else ""
    except:
        return ""

def farm_intelligence_tree(query):
    print(f"[*] Harvesting Intelligence for: {query}")
    rss_url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    
    try:
        response = requests.get(rss_url, timeout=10)
        root = ET.fromstring(response.content)
        items = root.findall('.//item')
        
        unique_articles = {}
        hashtag_pool = set()
        
        for item in items[:12]:
            title = item.find('title').text if item.find('title') is not None else ""
            link = item.find('link').text if item.find('link') is not None else ""
            desc = item.find('description').text if item.find('description') is not None else ""
            
            source_tag = item.find('source')
            source_name = source_tag.text if source_tag is not None else "Web"
            
            article_hash = hashlib.md5(title.encode('utf-8')).hexdigest()
            
            if article_hash not in unique_articles:
                # Resolve final URL and extract thumbnail
                clean_url = resolve_target_url(link)
                img_url = extract_thumbnail_from_rss(desc)
                
                # Dynamic Hashtag Generation
                words = re.findall(r'\b[A-Z][a-zA-Z]+\b', title)
                for w in words:
                    if len(w) > 3 and w.upper() not in ["NEWS", "INDIA", "TIMES", "LATEST"]:
                        hashtag_pool.add(f"#{w.upper()}")
                
                unique_articles[article_hash] = {
                    "title": title,
                    "url": clean_url,
                    "source": source_name,
                    "image": img_url # Populating this is critical for the new frontend!
                }

        return {
            "topic": query,
            "diversity_score": min(len(unique_articles) * 7, 100),
            "unique_links_count": len(unique_articles),
            "hashtags": list(hashtag_pool)[:8],
            "links": list(unique_articles.values())
        }

    except Exception as e:
        print(f"[-] Harvester error: {e}")
        return None

def push_tree_to_live_worker(payload):
    worker_url = "https://thenewsdip-backend.thenewsdip.workers.dev/api/update"
    secret = os.environ.get("API_SECRET_KEY", "MySuperSecretDipEngineToken123!")
    
    print(f"[*] Pushing data to Cloudflare...")
    try:
        requests.put(worker_url, headers={"Authorization": f"Bearer {secret}"}, json=payload, timeout=15)
        print("✓ Platform synchronized.")
    except Exception as e:
        print(f"✗ Sync failed: {e}")

if __name__ == "__main__":
    # Updated: Now harvesting live trending topics automatically
    from __main__ import get_live_trends # Reuse the trends function we defined earlier
    
    targets = get_live_trends() # This grabs REAL trends from Google
    final_payload = [farm_intelligence_tree(t) for t in targets if farm_intelligence_tree(t)]
    
    if final_payload:
        push_tree_to_live_worker(final_payload)
