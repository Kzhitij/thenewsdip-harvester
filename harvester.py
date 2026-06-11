import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import urllib.parse
import json
import requests
import spacy

nlp = spacy.load("en_core_web_sm")

# News publishers extracted by NLP as ORG entities are noise — skip them
PUBLISHER_BLOCKLIST = {
    'times of india','the times of india','toi','ndtv','ndtv india',
    'hindustan times','the hindu','indian express','the indian express',
    'economic times','the economic times','livemint','live mint','mint',
    'business standard','moneycontrol','news18','zee news','india today',
    'firstpost','scroll','scroll.in','the wire','the print','outlook india',
    'outlook','wion','cnbc tv18','cnbctv18','bloomberg','bloomberg quint',
    'bq prime','reuters','pti','ani','ians','bbc','cnn','ap',
    'deccan herald','deccan chronicle','tribune india','the tribune',
    'patrika','dainik jagran','dainik bhaskar','navbharat times',
    'mathrubhumi','manorama','dinamalar','dinamani','eenadu','sakshi',
    'samayam','loksatta','lokmat','maharashtra times','ananda bazar',
    'anandabazar','punjab kesari','mid-day','midday','mumbai mirror',
    'google','twitter','facebook','meta','instagram','whatsapp','youtube',
    'microsoft','amazon','apple','openai','india','indian','government',
    'press trust','united news','asian news',
}

RSS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TheNewsDip-Harvester/2.0; +https://www.thenewsdip.com/about)"
}

# Primary Google News feeds + fallback direct RSS feeds
FEEDS = [
    "https://news.google.com/rss/search?q=India+latest+news&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=India+economy+politics&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/sections/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0ZqcEJVaTloV0Vnd09BTVM_hl=en-IN&gl=IN&ceid=IN:en",
    # Reliable direct RSS fallbacks
    "https://feeds.feedburner.com/ndtvnews-top-stories",
    "https://www.thehindu.com/news/national/feeder/default.rss",
    "https://indianexpress.com/feed/",
    "https://www.livemint.com/rss/news",
    "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
]


def clean_url(url):
    parsed = urllib.parse.urlparse(url)
    clean_params = {k: v for k, v in urllib.parse.parse_qs(parsed.query).items()
                    if not k.startswith("utm_")}
    new_query = urllib.parse.urlencode(clean_params, doseq=True)
    return urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment)
    )


def parse_pub_date(date_str):
    if not date_str:
        return datetime.now(timezone.utc)
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z",
                "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return datetime.now(timezone.utc)


def harvest_and_process():
    raw_articles = []
    seen_urls = set()
    now = datetime.now(timezone.utc)
    cutoff_time = now - timedelta(hours=24)
    feeds_ok = 0

    for feed_url in FEEDS:
        try:
            resp = requests.get(feed_url, headers=RSS_HEADERS, timeout=14)
            if resp.status_code != 200:
                print(f"  SKIP {feed_url[:60]}: HTTP {resp.status_code}")
                continue

            root = ET.fromstring(resp.content)
            items = root.findall(".//item")
            added = 0

            for item in items:
                title_el = item.find("title")
                link_el  = item.find("link")
                pub_el   = item.find("pubDate")

                title      = (title_el.text or "").strip() if title_el is not None else ""
                link       = (link_el.text  or "").strip() if link_el  is not None else ""
                pub_str    = (pub_el.text   or "").strip() if pub_el   is not None else ""

                if not title or not link:
                    continue

                clean_link = clean_url(link)
                domain     = urllib.parse.urlparse(clean_link).netloc.replace("www.", "")
                pub_date   = parse_pub_date(pub_str)

                if pub_date >= cutoff_time and clean_link not in seen_urls:
                    seen_urls.add(clean_link)
                    raw_articles.append({
                        "title":     title,
                        "link":      clean_link,
                        "domain":    domain,
                        "age_hours": round((now - pub_date).total_seconds() / 3600, 2),
                    })
                    added += 1

            feeds_ok += 1
            print(f"  OK  {feed_url[:60]}: {len(items)} items → {added} fresh")

        except ET.ParseError as e:
            print(f"  ERR {feed_url[:60]}: XML parse — {e}")
        except requests.RequestException as e:
            print(f"  ERR {feed_url[:60]}: Network — {e}")
        except Exception as e:
            print(f"  ERR {feed_url[:60]}: {e}")

    print(f"\nHarvested {len(raw_articles)} fresh articles from {feeds_ok}/{len(FEEDS)} feeds")

    # Entity extraction → hashtag mapping
    hashtag_map = defaultdict(list)
    for article in raw_articles:
        doc = nlp(article["title"])
        valid_entities = set()
        for ent in doc.ents:
            if ent.label_ in ("PERSON", "ORG", "GPE", "EVENT", "PRODUCT", "NORP"):
                if ent.text.lower().strip() in PUBLISHER_BLOCKLIST:
                    continue
                tag = "#" + "".join(c for c in ent.text.title() if c.isalnum())
                if len(tag) > 3:
                    valid_entities.add(tag)
        for tag in valid_entities:
            hashtag_map[tag].append(article)

    # Grade and score each hashtag cluster
    graded_tree = []
    for tag, articles in hashtag_map.items():
        unique_domains  = {a["domain"] for a in articles}
        total_links     = len(articles)
        src_diversity   = len(unique_domains)
        avg_age         = sum(a["age_hours"] for a in articles) / total_links
        velocity        = sum(1 for a in articles if a["age_hours"] <= 3)
        final_score     = int(total_links * 10 + src_diversity * 15 + velocity * 20 - avg_age * 2)

        graded_tree.append({
            "hashtag":         tag,
            "score":           max(final_score, 1),
            "link_count":      total_links,
            "source_diversity": src_diversity,
            "articles":        articles[:10],
        })

    graded_tree.sort(key=lambda x: x["score"], reverse=True)
    print(f"Generated {len(graded_tree)} hashtag clusters (top 25 will be published)")
    return graded_tree


def publish_outputs(tree_data):
    payload = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "tree": tree_data,
    }
    with open("news_tree.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print("✓ news_tree.json written")
    return json.dumps(payload)


def push_tree_to_live_worker(json_payload):
    worker_url = "https://thenewsdip-backend.thenewsdip.workers.dev/api/update"
    secret_key = os.environ.get("API_SECRET_KEY")

    if not secret_key:
        print("✗ API_SECRET_KEY not set — Cloudflare sync skipped")
        return False

    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type":  "application/json",
        "User-Agent":    "TheNewsDip-Harvester/2.0",
    }

    print(f"Pushing to Cloudflare Worker ({worker_url})...")
    try:
        resp = requests.put(worker_url, headers=headers, data=json_payload, timeout=20)
        if resp.status_code == 200:
            print("✓ Cloudflare Worker updated successfully")
            return True
        print(f"✗ Worker update failed: HTTP {resp.status_code} — {resp.text[:300]}")
        return False
    except requests.Timeout:
        print("✗ Worker update timed out after 20s")
        return False
    except requests.RequestException as e:
        print(f"✗ Worker update network error: {e}")
        return False


if __name__ == "__main__":
    print("=" * 55)
    print("TheNewsDip Harvester v2.0 — starting run")
    print("=" * 55)

    data_tree = harvest_and_process()

    if data_tree:
        json_payload = publish_outputs(data_tree)
        pushed = push_tree_to_live_worker(json_payload)
        status = "synced to Cloudflare ✓" if pushed else "Cloudflare sync skipped"
        print(f"\n✓ Run complete: {len(data_tree)} trends, {status}")
    else:
        print("\n⚠ No articles harvested — RSS feeds may be blocked or empty")
        print("  Cloudflare Worker NOT updated this run")
