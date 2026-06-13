import os
import re
import html
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import urllib.parse
import json
import requests
import spacy

nlp = spacy.load("en_core_web_sm")

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
    'press trust','united news','asian news','techcrunch','verge','wired',
    'guardian','aljazeera','al jazeera',
}

RSS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TheNewsDip-Harvester/2.0; +https://www.thenewsdip.com/about)"
}

MEDIA_NS  = 'http://search.yahoo.com/mrss/'
CONTENT_NS = 'http://purl.org/rss/1.0/modules/content/'

# ── Categorised feed sources ─────────────────────────────────────────────────
FEED_SOURCES = {
    'india': [
        ('TOI',            'https://timesofindia.indiatimes.com/rssfeedstopstories.cms'),
        ('NDTV',           'https://feeds.feedburner.com/ndtvnews-top-stories'),
        ('The Hindu',      'https://www.thehindu.com/news/national/feeder/default.rss'),
        ('Indian Express', 'https://indianexpress.com/feed/'),
        ('Hindustan Times','https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml'),
        ('News18',         'https://www.news18.com/rss/india.xml'),
        ('Scroll.in',      'https://scroll.in/feed'),
        ('The Wire',       'https://thewire.in/feed'),
        ('NDTV India',     'https://news.google.com/rss/search?q=India+latest+news&hl=en-IN&gl=IN&ceid=IN:en'),
        ('India Politics', 'https://news.google.com/rss/search?q=India+politics+economy&hl=en-IN&gl=IN&ceid=IN:en'),
    ],
    'world': [
        ('BBC World',      'https://feeds.bbci.co.uk/news/world/rss.xml'),
        ('BBC Top',        'https://feeds.bbci.co.uk/news/rss.xml'),
        ('Al Jazeera',     'https://www.aljazeera.com/xml/rss/all.xml'),
        ('DW English',     'https://rss.dw.com/rdf/rss-en-all'),
        ('GNews World',    'https://news.google.com/rss/search?q=world+news+international&hl=en-IN&gl=IN&ceid=IN:en'),
        ('GNews Geopolit', 'https://news.google.com/rss/search?q=global+geopolitics+war+diplomacy+UN&hl=en-IN&gl=IN&ceid=IN:en'),
        ('GNews USA EU',   'https://news.google.com/rss/search?q=USA+Europe+China+Russia+Middle+East+news&hl=en-IN&gl=IN&ceid=IN:en'),
    ],
    'business': [
        ('Economic Times', 'https://economictimes.indiatimes.com/rssfeedstopstories.cms'),
        ('ET Markets',     'https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms'),
        ('Business Std',   'https://www.business-standard.com/rss/home_page_top_stories.rss'),
        ('Moneycontrol',   'https://www.moneycontrol.com/rss/latestnews.xml'),
        ('GNews Business', 'https://news.google.com/rss/search?q=India+economy+business+markets&hl=en-IN&gl=IN&ceid=IN:en'),
        ('GNews Finance',  'https://news.google.com/rss/search?q=sensex+nifty+stock+market+RBI+rupee&hl=en-IN&gl=IN&ceid=IN:en'),
        ('GNews Global Biz','https://news.google.com/rss/search?q=global+economy+trade+GDP+inflation&hl=en-IN&gl=IN&ceid=IN:en'),
    ],
    'sports': [
        ('BBC Sport',      'https://feeds.bbci.co.uk/sport/rss.xml'),
        ('ESPNcricinfo',   'https://www.espncricinfo.com/rss/content/story/feeds/0.xml'),
        ('GNews Cricket',  'https://news.google.com/rss/search?q=cricket+IPL+India+match+T20+ODI&hl=en-IN&gl=IN&ceid=IN:en'),
        ('GNews Sports',   'https://news.google.com/rss/search?q=sports+football+badminton+kabaddi+hockey+India&hl=en-IN&gl=IN&ceid=IN:en'),
        ('GNews Intl Spt', 'https://news.google.com/rss/search?q=Olympics+tennis+chess+formula1+sports&hl=en-IN&gl=IN&ceid=IN:en'),
    ],
    'tech': [
        ('TechCrunch',     'https://techcrunch.com/feed/'),
        ('The Verge',      'https://www.theverge.com/rss/index.xml'),
        ('Ars Technica',   'https://feeds.arstechnica.com/arstechnica/index'),
        ('Gadgets360',     'https://www.gadgets360.com/rss/news'),
        ('GNews Tech',     'https://news.google.com/rss/search?q=technology+AI+smartphones+India+startup&hl=en-IN&gl=IN&ceid=IN:en'),
        ('GNews AI',       'https://news.google.com/rss/search?q=artificial+intelligence+ChatGPT+OpenAI+semiconductor&hl=en-IN&gl=IN&ceid=IN:en'),
    ],
    'entertainment': [
        ('Hollywood Rep',   'https://www.hollywoodreporter.com/feed/'),
        ('Variety',         'https://variety.com/feed/'),
        ('Pinkvilla',       'https://www.pinkvilla.com/feed'),
        ('GNews Bollywood', 'https://news.google.com/rss/search?q=bollywood+movies+OTT+India+film+trailer&hl=en-IN&gl=IN&ceid=IN:en'),
        ('GNews Hollywood', 'https://news.google.com/rss/search?q=Hollywood+film+celebrity+music+Grammy+Oscar&hl=en-IN&gl=IN&ceid=IN:en'),
    ],
}

# Flat list of legacy feeds kept for hashtag intelligence (existing behaviour)
LEGACY_FEEDS = [
    "https://news.google.com/rss/search?q=India+latest+news&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=India+economy+politics&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/sections/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0ZqcEJVaTloV0Vnd09BTVM_hl=en-IN&gl=IN&ceid=IN:en",
    "https://feeds.feedburner.com/ndtvnews-top-stories",
    "https://www.thehindu.com/news/national/feeder/default.rss",
    "https://indianexpress.com/feed/",
    "https://www.livemint.com/rss/news",
    "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
]

# Domain → category overrides
DOMAIN_CATEGORY = {
    'espncricinfo.com': 'sports', 'cricbuzz.com': 'sports',
    'sportskeeda.com': 'sports',  'espn.com': 'sports',
    'bbc.co.uk/sport': 'sports',  'goal.com': 'sports',
    'techcrunch.com': 'tech',     'theverge.com': 'tech',
    'wired.com': 'tech',          'gadgets360.com': 'tech',
    'arstechnica.com': 'tech',    'technologyreview.com': 'tech',
    'ndtvgadgets.com': 'tech',
    'economictimes.indiatimes.com': 'business',
    'moneycontrol.com': 'business', 'livemint.com': 'business',
    'business-standard.com': 'business', 'businesstoday.in': 'business',
    'cnbctv18.com': 'business',   'bloombergquint.com': 'business',
    'bollywoodhungama.com': 'entertainment', 'pinkvilla.com': 'entertainment',
    'filmfare.com': 'entertainment', 'hollywoodreporter.com': 'entertainment',
    'variety.com': 'entertainment',
    'bbc.co.uk': 'world', 'aljazeera.com': 'world',
    'theguardian.com': 'world',   'reuters.com': 'world',
    'dw.com': 'world',            'france24.com': 'world',
    'apnews.com': 'world',
    'timesofindia.indiatimes.com': 'india',
    'ndtv.com': 'india',          'thehindu.com': 'india',
    'indianexpress.com': 'india', 'hindustantimes.com': 'india',
    'news18.com': 'india',        'scroll.in': 'india',
    'thewire.in': 'india',
}

# Keyword → category (for articles from mixed sources)
KEYWORD_CATEGORY = {
    'sports': [
        'cricket','ipl','t20','test match','odi','wicket','batting','bowling',
        'fifa','football','soccer','goal','tournament','league','champion',
        'olympic','medal','tennis','badminton','chess','kabaddi',
    ],
    'business': [
        'sensex','nifty','stock market','rupee','rbi','inflation','gdp',
        'economy','budget','tax','ipo','investment','startup','trade',
        'profit','revenue','quarterly','earnings','interest rate','fed',
    ],
    'tech': [
        'artificial intelligence','machine learning','chatgpt','openai',
        'smartphone','5g','app','software','cybersecurity','data breach',
        'elon musk','tesla','spacex','google','meta ai','samsung galaxy',
    ],
    'entertainment': [
        'bollywood','film','movie','actor','actress','celebrity','music',
        'album','award','oscar','grammy','box office','trailer','release',
        'web series','netflix','amazon prime','disney',
    ],
}


# ── RSS parsing helpers ───────────────────────────────────────────────────────

def extract_image(item):
    """Try multiple conventions to find an image URL from an RSS item."""
    # media:content
    mc = item.find(f'{{{MEDIA_NS}}}content')
    if mc is not None:
        url = mc.get('url', '')
        med = mc.get('medium', '')
        if url and (med in ('image','') or any(e in url.lower() for e in ('.jpg','.jpeg','.png','.webp'))):
            return url
    # media:thumbnail
    mt = item.find(f'{{{MEDIA_NS}}}thumbnail')
    if mt is not None and mt.get('url'):
        return mt.get('url')
    # enclosure
    enc = item.find('enclosure')
    if enc is not None and 'image' in enc.get('type','') and enc.get('url'):
        return enc.get('url')
    # img tag inside <description>
    desc_el = item.find('description')
    if desc_el is not None and desc_el.text:
        m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', desc_el.text)
        if m and m.group(1).startswith('http'):
            return m.group(1)
    return None


def extract_desc(item):
    """Extract plain-text description from RSS item (strip HTML, truncate)."""
    for tag in ('description', f'{{{CONTENT_NS}}}encoded', 'summary'):
        el = item.find(tag)
        if el is not None and el.text:
            text = re.sub(r'<[^>]+>', ' ', el.text)
            text = html.unescape(text)
            text = re.sub(r'\s+', ' ', text).strip()
            # Remove source suffix sometimes appended to descriptions
            text = re.sub(r'\s*-\s*(TOI|NDTV|BBC|Reuters|ET|HT)\s*$', '', text)
            return text[:220] if len(text) > 220 else text
    return ''


def clean_url(url):
    parsed = urllib.parse.urlparse(url)
    clean_params = {k: v for k, v in urllib.parse.parse_qs(parsed.query).items()
                    if not k.startswith('utm_')}
    new_query = urllib.parse.urlencode(clean_params, doseq=True)
    return urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment)
    )


def parse_pub_date(date_str):
    if not date_str:
        return datetime.now(timezone.utc)
    for fmt in ('%a, %d %b %Y %H:%M:%S %Z', '%a, %d %b %Y %H:%M:%S %z',
                '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S%z'):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return datetime.now(timezone.utc)


def infer_category(domain, title, feed_cat):
    """Determine article category from domain overrides, feed category, or keywords."""
    # 1. Domain override
    for d, cat in DOMAIN_CATEGORY.items():
        if d in domain:
            return cat
    # 2. Feed category (trusted)
    if feed_cat in ('india', 'world', 'business', 'sports', 'tech', 'entertainment'):
        return feed_cat
    # 3. Title keywords
    title_lower = title.lower()
    for cat, keywords in KEYWORD_CATEGORY.items():
        if any(kw in title_lower for kw in keywords):
            return cat
    # 4. Default
    return 'india'


def fetch_feed(source_name, url, feed_cat, cutoff_time, seen_urls):
    """Fetch a single RSS feed and return a list of article dicts."""
    articles = []
    now = datetime.now(timezone.utc)
    try:
        resp = requests.get(url, headers=RSS_HEADERS, timeout=14)
        if resp.status_code != 200:
            print(f'  SKIP [{source_name}] HTTP {resp.status_code}')
            return articles
        root = ET.fromstring(resp.content)
        # Support both RSS 2.0 (<item>) and Atom (<entry>) formats
        ATOM = 'http://www.w3.org/2005/Atom'
        items = root.findall('.//item') or root.findall(f'.//{{{ATOM}}}entry')
        is_atom = not root.findall('.//item') and bool(items)
        added = 0
        for item in items:
            title_el = item.find('title') or item.find(f'{{{ATOM}}}title')
            pub_el   = (item.find('pubDate') or item.find('{http://purl.org/dc/elements/1.1/}date')
                        or item.find(f'{{{ATOM}}}published') or item.find(f'{{{ATOM}}}updated'))
            if is_atom:
                link_el = item.find(f'{{{ATOM}}}link[@rel="alternate"]') or item.find(f'{{{ATOM}}}link')
                link = (link_el.get('href', '') if link_el is not None else '')
            else:
                link_el = item.find('link')
                link = (link_el.text or '').strip() if link_el is not None else ''

            title   = (title_el.text or '').strip() if title_el is not None else ''
            pub_str = (pub_el.text   or '').strip() if pub_el   is not None else ''

            if not title or not link:
                continue
            # Remove "Source - Title" Google News format
            if ' - ' in title:
                parts = title.rsplit(' - ', 1)
                title = parts[0].strip()

            clean_link = clean_url(link)
            domain     = urllib.parse.urlparse(clean_link).netloc.replace('www.', '')
            pub_date   = parse_pub_date(pub_str)

            if pub_date >= cutoff_time and clean_link not in seen_urls:
                seen_urls.add(clean_link)
                image = extract_image(item)
                desc  = extract_desc(item)
                cat   = infer_category(domain, title, feed_cat)

                articles.append({
                    'title':     title,
                    'url':       clean_link,
                    'domain':    domain,
                    'source':    source_name,
                    'image':     image,
                    'desc':      desc,
                    'category':  cat,
                    'age_hours': round((now - pub_date).total_seconds() / 3600, 2),
                    'pub_time':  pub_date.isoformat(),
                })
                added += 1
        print(f'  OK  [{source_name}] {len(items)} items → {added} fresh')
    except ET.ParseError as e:
        print(f'  ERR [{source_name}] XML parse — {e}')
    except requests.RequestException as e:
        print(f'  ERR [{source_name}] Network — {e}')
    except Exception as e:
        print(f'  ERR [{source_name}] {e}')
    return articles


# ── Guardian API (free test key: 5 000 req/day) ───────────────────────────────
def fetch_guardian_highlights():
    """Fetch top Guardian stories for the world/business/tech categories."""
    articles = []
    now = datetime.now(timezone.utc)
    sections = [
        ('world',    'world'),
        ('business', 'business'),
        ('tech',     'technology'),
    ]
    base = 'https://content.guardianapis.com'
    params_base = 'show-fields=thumbnail,trailText&order-by=newest&page-size=10&api-key=test'
    for cat, section in sections:
        try:
            url = f'{base}/{section}?{params_base}'
            r = requests.get(url, headers=RSS_HEADERS, timeout=12)
            if not r.ok:
                continue
            d = r.json()
            for item in d.get('response', {}).get('results', []):
                fields = item.get('fields', {})
                pub_str = item.get('webPublicationDate', '')
                try:
                    pub_date = datetime.fromisoformat(pub_str.replace('Z', '+00:00'))
                except Exception:
                    pub_date = now
                articles.append({
                    'title':    item.get('webTitle', ''),
                    'url':      item.get('webUrl', ''),
                    'domain':   'theguardian.com',
                    'source':   'The Guardian',
                    'image':    fields.get('thumbnail', None),
                    'desc':     fields.get('trailText', ''),
                    'category': cat,
                    'age_hours': round((now - pub_date).total_seconds() / 3600, 2),
                    'pub_time': pub_date.isoformat(),
                })
        except Exception as e:
            print(f'  ERR [Guardian/{section}] {e}')
    print(f'  OK  [Guardian] {len(articles)} articles')
    return articles


# ── Main harvesting pipeline ──────────────────────────────────────────────────

def harvest_homepage_feed():
    """Harvest all categorised RSS sources + Guardian. Returns homepage_feed dict."""
    now        = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_2h  = now - timedelta(hours=2)
    seen_urls  = set()

    all_articles = []

    for feed_cat, sources in FEED_SOURCES.items():
        print(f'\n  Category: {feed_cat.upper()}')
        for source_name, url in sources:
            arts = fetch_feed(source_name, url, feed_cat, cutoff_24h, seen_urls)
            all_articles.extend(arts)

    # Guardian API highlights
    print('\n  Category: GUARDIAN API')
    all_articles.extend(fetch_guardian_highlights())

    # Deduplicate by title similarity (same headline from 2 sources)
    deduped = []
    title_keys = set()
    for a in all_articles:
        key = re.sub(r'[^a-z0-9]', '', a['title'].lower())[:40]
        if key not in title_keys:
            title_keys.add(key)
            deduped.append(a)

    # Sort by age (freshest first)
    deduped.sort(key=lambda x: x['age_hours'])

    # Breaking = articles from last 2 hours
    breaking = [a for a in deduped if a['age_hours'] <= 2][:15]

    print(f'\n  Total articles: {len(deduped)} | Breaking (≤2h): {len(breaking)}')

    return {
        'last_updated': now.isoformat(),
        'breaking':     breaking,
        'articles':     deduped[:200],   # cap at 200 for KV size
    }


def harvest_and_process():
    """Original harvester for hashtag intelligence tree (backward-compatible)."""
    raw_articles = []
    seen_urls    = set()
    now          = datetime.now(timezone.utc)
    cutoff_time  = now - timedelta(hours=24)
    feeds_ok     = 0

    for feed_url in LEGACY_FEEDS:
        try:
            resp = requests.get(feed_url, headers=RSS_HEADERS, timeout=14)
            if resp.status_code != 200:
                print(f'  SKIP {feed_url[:60]}: HTTP {resp.status_code}')
                continue

            root  = ET.fromstring(resp.content)
            items = root.findall('.//item')
            added = 0

            for item in items:
                title_el = item.find('title')
                link_el  = item.find('link')
                pub_el   = item.find('pubDate')

                title   = (title_el.text or '').strip() if title_el is not None else ''
                link    = (link_el.text  or '').strip() if link_el  is not None else ''
                pub_str = (pub_el.text   or '').strip() if pub_el   is not None else ''

                if not title or not link:
                    continue

                clean_link = clean_url(link)
                domain     = urllib.parse.urlparse(clean_link).netloc.replace('www.', '')
                pub_date   = parse_pub_date(pub_str)

                if pub_date >= cutoff_time and clean_link not in seen_urls:
                    seen_urls.add(clean_link)
                    raw_articles.append({
                        'title':     title,
                        'link':      clean_link,
                        'domain':    domain,
                        'age_hours': round((now - pub_date).total_seconds() / 3600, 2),
                    })
                    added += 1

            feeds_ok += 1
            print(f'  OK  {feed_url[:60]}: {len(items)} items → {added} fresh')

        except ET.ParseError as e:
            print(f'  ERR {feed_url[:60]}: XML parse — {e}')
        except requests.RequestException as e:
            print(f'  ERR {feed_url[:60]}: Network — {e}')
        except Exception as e:
            print(f'  ERR {feed_url[:60]}: {e}')

    print(f'\nHarvested {len(raw_articles)} fresh articles from {feeds_ok}/{len(LEGACY_FEEDS)} feeds')

    # Entity extraction → hashtag mapping
    hashtag_map = defaultdict(list)
    for article in raw_articles:
        doc = nlp(article['title'])
        valid_entities = set()
        for ent in doc.ents:
            if ent.label_ in ('PERSON', 'ORG', 'GPE', 'EVENT', 'PRODUCT', 'NORP'):
                if ent.text.lower().strip() in PUBLISHER_BLOCKLIST:
                    continue
                tag = '#' + ''.join(c for c in ent.text.title() if c.isalnum())
                if len(tag) > 3:
                    valid_entities.add(tag)
        for tag in valid_entities:
            hashtag_map[tag].append(article)

    graded_tree = []
    for tag, articles in hashtag_map.items():
        unique_domains  = {a['domain'] for a in articles}
        total_links     = len(articles)
        src_diversity   = len(unique_domains)
        avg_age         = sum(a['age_hours'] for a in articles) / total_links
        velocity        = sum(1 for a in articles if a['age_hours'] <= 3)
        final_score     = int(total_links * 10 + src_diversity * 15 + velocity * 20 - avg_age * 2)

        graded_tree.append({
            'hashtag':          tag,
            'score':            max(final_score, 1),
            'link_count':       total_links,
            'source_diversity': src_diversity,
            'articles':         articles[:10],
        })

    graded_tree.sort(key=lambda x: x['score'], reverse=True)
    print(f'Generated {len(graded_tree)} hashtag clusters (top 25 will be published)')
    return graded_tree


def publish_outputs(tree_data):
    payload = {
        'last_updated': datetime.now(timezone.utc).isoformat(),
        'tree': tree_data,
    }
    with open('news_tree.json', 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print('✓ news_tree.json written')
    return json.dumps(payload)


def push_to_worker(endpoint_path, json_payload, label='data'):
    worker_url = f'https://thenewsdip-backend.thenewsdip.workers.dev{endpoint_path}'
    secret_key = os.environ.get('API_SECRET_KEY')
    if not secret_key:
        print(f'✗ API_SECRET_KEY not set — {label} sync skipped')
        return False
    headers = {
        'Authorization': f'Bearer {secret_key}',
        'Content-Type':  'application/json',
        'User-Agent':    'TheNewsDip-Harvester/2.0',
    }
    print(f'Pushing {label} to {worker_url}...')
    try:
        resp = requests.put(worker_url, headers=headers, data=json_payload, timeout=20)
        if resp.status_code == 200:
            print(f'✓ {label} pushed successfully')
            return True
        print(f'✗ {label} push failed: HTTP {resp.status_code} — {resp.text[:300]}')
        return False
    except requests.Timeout:
        print(f'✗ {label} push timed out')
        return False
    except requests.RequestException as e:
        print(f'✗ {label} push error: {e}')
        return False


if __name__ == '__main__':
    print('=' * 60)
    print('TheNewsDip Harvester v3.0 — starting run')
    print('=' * 60)

    # ── Part 1: Homepage feed (new) ───────────────────────────────────────────
    print('\n[1/2] Harvesting homepage feed (categorised RSS + Guardian)...')
    feed_data = harvest_homepage_feed()
    feed_payload = json.dumps(feed_data, ensure_ascii=False)
    push_to_worker('/api/update-feed', feed_payload, 'homepage feed')

    # ── Part 2: Hashtag intelligence tree (original) ─────────────────────────
    print('\n[2/2] Harvesting hashtag intelligence tree...')
    data_tree = harvest_and_process()
    if data_tree:
        json_payload = publish_outputs(data_tree)
        push_to_worker('/api/update', json_payload, 'news tree')

    total = len(feed_data.get('articles', []))
    print(f'\n✓ Run complete: {total} feed articles, {len(data_tree)} hashtag trends')
