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
    """
    Follows the Google News redirect tracking link to obtain 
    the actual, direct destination publisher URL.
    """
    try:
        response = requests.get(google_rss_url, timeout=5, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        return response.url
    except Exception as e:
        print(f"[-] URL tracking resolution failed: {e}")
        return google_rss_url

def extract_thumbnail_from_rss(description_html):
    """
    Scavenges the hidden image thumbnail embedded inside 
    the Google News RSS description CDATA payload.
    """
    if not description_html:
        return ""
    try:
        # Strategy A: Regex match for image tags
        img_match = re.search(r'<img[^>]+src="([^">]+)"', description_html)
        if img_match:
            return img_match.group(1)
        
        # Strategy B: BS4 fallback parsing
        soup = BeautifulSoup(description_html, 'html.parser')
        img_tag = soup.find('img')
        if img_tag and img_tag.get('src'):
            return img_tag['src']
    except Exception as e:
        print(f"[-] Failed extraction of thumbnail asset: {e}")
    return ""

def farm_intelligence_tree(query):
    """
    Connects to the real RSS aggregator streams, pulls live data arrays,
    extracts parameters, and structures the core Quant Engine payload.
    """
    print(f"[*] Launching Harvester Engine for query: {query}")
    rss_url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    
    try:
        response = requests.get(rss_url, timeout=10)
        if response.status_code != 200:
            print(f"[-] Aggregator returned status code: {response.status_code}")
            return None
        
        # Parse XML structure natively
        root = ET.fromstring(response.content)
        items = root.findall('.//item')
        
        unique_articles = {}
        source_distribution = {}
        hashtag_pool = set()
        
        # Process top filtered inputs
        for item in items[:15]:
            title = item.find('title').text if item.find('title') is not None else "Untitled Intelligence"
            link = item.find('link').text if item.find('link') is not None else ""
            desc = item.find('description').text if item.find('description') is not None else ""
            pub_date = item.find('pubDate').text if item.find('pubDate') is not None else "Recent"
            
            # Extract source authority name
            source_tag = item.find('source')
            source_name = source_tag.text if source_tag is not None else "Global Intelligence Network"
            
            if not link:
                continue
                
            # Create immutable deterministic payload fingerprints
            article_hash = hashlib.md5(title.encode('utf-8')).hexdigest()
            
            if article_hash not in unique_articles:
                # Follow redirects to map original nodes
                clean_url = resolve_target_url(link)
                img_url = extract_thumbnail_from_rss(desc)
                
                # Update source weight index
                source_distribution[source_name] = source_distribution.get(source_name, 0) + 1
                
                # Generate tracking tags from titles
                words = re.findall(r'\b[A-Z][a-zA-Z]+\b', title)
                for word in words:
                    if len(word) > 3 and word.upper() not in ["NEWS", "INDIA", "TIMES", "LATEST"]:
                        hashtag_pool.add(f"#{word.upper()}")
                
                unique_articles[article_hash] = {
                    "title": title,
                    "url": clean_url,
                    "source": source_name,
                    "published": pub_date,
                    "image": img_url
                }

        # Calculate diversity matrices
        total_nodes = len(unique_articles)
        unique_sources = len(source_distribution)
        diversity_score = int((unique_sources / total_nodes) * 10) if total_nodes > 0 else 0
        
        # Construct unified structural payload
        intelligence_tree = {
            "query": query,
            "diversity_score": max(1, min(diversity_score, 10)),  # Clamp between 1-10
            "hashtag_footprint": " ".join(list(hashtag_pool)[:8]),
            "links": list(unique_articles.values())
        }
        
        return intelligence_tree

    except Exception as e:
        print(f"Critical execution error in Harvester Engine: {e}")
        return None

if __name__ == "__main__":
    # Test framework execution
    sample_node = farm_intelligence_tree("NSE F&O Regulations")
    if sample_node:
        print(json.dumps(sample_node, indent=2))
