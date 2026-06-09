import os  # Add this to your imports at the top
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from collections import Counter, defaultdict
import urllib.parse
import json
import requests
import spacy
from bs4 import BeautifulSoup

# Load lightweight NLP model for Entity Extraction
nlp = spacy.load("en_core_web_sm")

# Sample RSS Feeds (You can add global, national, and regional feeds here)
FEEDS = [
    "https://news.google.com/rss/search?q=latest&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/sections/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0ZqcEJVaTloV0Vnd09BTVM_hl=en-IN&gl=IN&ceid=IN:en"
]

def clean_url(url):
    """Removes tracking links/parameters to safely deduplicate URLs."""
    parsed = urllib.parse.urlparse(url)
    # Remove common tracking queries (like utm_source)
    query_params = urllib.parse.parse_qs(parsed.query)
    clean_params = {k: v for k, v in query_params.items() if not k.startswith('utm_')}
    new_query = urllib.parse.urlencode(clean_params, doseq=True)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))

def parse_pub_date(date_str):
    """Parses various RSS date formats into a standard datetime object."""
    formats = ["%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return datetime.utcnow()

def harvest_and_process():
    raw_articles = []
    seen_urls = set()
    now = datetime.utcnow()
    cutoff_time = now - timedelta(hours=24) # 24-hour rule strict filter

    # Fetch and parse XML
    for url in FEEDS:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code != 200: continue
            
            root = ET.fromstring(response.content)
            for item in root.findall(".//item"):
                title = item.find("title").text if item.find("title") is not None else ""
                link = item.find("link").text if item.find("link") is not None else ""
                pub_date_str = item.find("pubDate").text if item.find("pubDate") is not None else ""
                
                # Get clean domain name for source diversity checking
                clean_link = clean_url(link)
                domain = urllib.parse.urlparse(clean_link).netloc
                
                pub_date = parse_pub_date(pub_date_str)
                
                # Filter out stale news and exact link duplicates immediately
                if pub_date >= cutoff_time and clean_link not in seen_urls:
                    seen_urls.add(clean_link)
                    raw_articles.append({
                        "title": title,
                        "link": clean_link,
                        "domain": domain,
                        "age_hours": (now - pub_date).total_seconds() / 3600
                    })
        except Exception as e:
            print(f"Error processing feed {url}: {e}")

    # Step 2: Extract Entities & Map to Hashtags
    hashtag_map = defaultdict(list)
    
    for article in raw_articles:
        # Pass the headline through NLP engine
        doc = nlp(article["title"])
        
        # Pull out People, Organizations, and Geopolitical Entities
        valid_entities = []
        for ent in doc.ents:
            if ent.label_ in ["PERSON", "ORG", "GPE", "EVENT"]:
                # Convert string to a clean alphanumeric hashtag (e.g., "RBI Policy" -> "RBIPolicy")
                tag = "#" + "".join(e for e in ent.text.title() if e.isalnum())
                if len(tag) > 2: # Ignore single character artifacts
                    valid_entities.append(tag)
        
        # De-duplicate tags within the same headline
        for tag in set(valid_entities):
            hashtag_map[tag].append(article)

    # Step 3: Grade and Score the Hashtag Tree
    graded_tree = []
    
    for tag, articles in hashtag_map.items():
        unique_domains = set(a["domain"] for a in articles)
        total_links = len(articles)
        
        # Grading Algorithm Metrics
        source_diversity_score = len(unique_domains)
        avg_age = sum(a["age_hours"] for a in articles) / total_links
        velocity_score = sum(1 for a in articles if a["age_hours"] <= 3) # Weight fresh news heavily
        
        # Final weighted score
        final_score = int((total_links * 10) + (source_diversity_score * 15) + (velocity_score * 20) - (avg_age * 2))
        
        graded_tree.append({
            "hashtag": tag,
            "score": max(final_score, 1),
            "link_count": total_links,
            "source_diversity": source_diversity_score,
            "articles": articles[:10] # Cap out at top 10 links per tag to save storage bandwidth
        })
        
    # Sort tree globally so highest scoring trends sit at the absolute top
    graded_tree.sort(key=lambda x: x["score"], reverse=True)
    return graded_tree

def publish_outputs(tree_data):
    # 1. Output Structured JSON Document
    with open("news_tree.json", "w", encoding="utf-8") as f:
        json.dump({"last_updated": datetime.utcnow().isoformat(), "tree": tree_data}, f, indent=2, ensure_ascii=False)
    print("✓ Successfully published news_tree.json")

    # 2. Output Dynamic Minimalist HTML
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>thenewsdip | Trend Engine</title>
    <style>
        body {{ font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif; background: #fff; color: #111; max-width: 800px; margin: 40px auto; padding: 0 20px; }}
        header {{ border-bottom: 2px solid #111; padding-bottom: 20px; margin-bottom: 30px; }}
        h1 {{ font-family: 'Playfair Display', serif; font-size: 32px; margin: 0; }}
        h1 em {{ color: #c0000d; font-style: normal; }}
        .meta {{ font-size: 12px; color: #666; margin-top: 5px; }}
        .trend-card {{ border: 1px solid #eee; padding: 20px; margin-bottom: 15px; border-radius: 4px; transition: border-color 0.2s; }}
        .trend-card:hover {{ border-color: #c0000d; }}
        .trend-header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px dashed #eee; padding-bottom: 10px; margin-bottom: 12px; }}
        .hashtag {{ font-size: 18px; font-weight: bold; color: #111; text-decoration: none; }}
        .hashtag:hover {{ color: #c0000d; }}
        .badge {{ font-size: 11px; background: #f6f6f6; border: 1px solid #ddd; padding: 2px 8px; border-radius: 12px; font-weight: 600; }}
        .score-badge {{ border-color: #c0000d; color: #c0000d; background: #fff0f0; }}
        .link-list {{ list-style: none; padding: 0; margin: 0; }}
        .link-list li {{ margin-bottom: 8px; font-size: 14px; display: flex; align-items: baseline; }}
        .link-list li::before {{ content: "•"; color: #c0000d; font-weight: bold; display: inline-block; width: 1em; margin-left: -1em; }}
        .article-link {{ color: #333; text-decoration: none; line-height: 1.4; }}
        .article-link:hover {{ text-decoration: underline; color: #000; }}
        .source-tag {{ font-size: 11px; color: #888; margin-left: 8px; white-space: nowrap; }}
    </style>
</head>
<body>
    <header>
        <h1>the<em>news</em>dip</h1>
        <div class="meta">Trend-Tree Pipeline • Refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
    </header>
    <main>
    """

    for trend in tree_data[:25]: # Render top 25 active trends to HTML view
        html_content += f"""
        <div class="trend-card">
            <div class="trend-header">
                <a class="hashtag" href="#">{trend['hashtag']}</a>
                <div>
                    <span class="badge score-badge">Score: {trend['score']}</span>
                    <span class="badge">{trend['link_count']} unique links</span>
                    <span class="badge">{trend['source_diversity']} sources</span>
                </div>
            </div>
            <ul class="link-list">
        """
        for article in trend["articles"]:
            html_content += f"""
                <li>
                    <a href="{article['link']}" class="article-link" target="_blank">{article['title'].split(' - ')[0]}</a>
                    <span class="source-tag">({article['domain']})</span>
                </li>
            """
        html_content += """
            </ul>
        </div>
        """

    html_content += """
    </main>
</body>
</html>
    """

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("✓ Successfully published index.html dashboard")

if __name__ == "__main__":
    print("Harvesting and structural tokenization processing initiated...")
    data_tree = harvest_and_process()
    publish_outputs(data_tree)

def push_tree_to_live_worker(tree_data):
    worker_url = "https://thenewsdip-backend.thenewsdip.workers.dev/api/update"
    
    # Securely pulls the secret from GitHub's hidden environment variables
    secret_key = os.environ.get("API_SECRET_KEY") 
    
    if not secret_key:
        print("✗ Critical Error: API_SECRET_KEY environmental variable missing.")
        return

    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json"
    }
    
    payload = json.dumps(tree_data)
    
    print(f"Pushing data tree to edge network at {worker_url}...")
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
    data_tree = harvest_and_process() # or whatever your main scraping function is named
    publish_outputs(data_tree)           
    push_tree_to_live_worker(data_tree)  # <--- THIS IS THE CRITICAL LINE MISSING ON GITHUB
