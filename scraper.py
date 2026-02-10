import re
import os
import json
from urllib.parse import urlparse, urljoin, urldefrag
from bs4 import BeautifulSoup
from collections import defaultdict

# ============================================================
# DATA COLLECTION (for the report)
# ============================================================
# These globals collect stats as the crawler runs.
# After crawling, you can inspect them to answer report questions.

unique_pages = set()            # All unique URLs visited (defragmented)
word_counts = defaultdict(int)  # word -> total count across all pages
longest_page = ("", 0)          # (url, word_count) of longest page
subdomain_pages = defaultdict(set)  # subdomain -> set of URLs found there

# File to periodically save progress
STATS_FILE = "crawl_stats.json"

# ============================================================
# STOP WORDS (common English words to ignore in word counting)
# ============================================================
STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an",
    "and", "any", "are", "aren't", "as", "at", "be", "because", "been",
    "before", "being", "below", "between", "both", "but", "by", "can't",
    "cannot", "could", "couldn't", "did", "didn't", "do", "does", "doesn't",
    "doing", "don't", "down", "during", "each", "few", "for", "from",
    "further", "had", "hadn't", "has", "hasn't", "have", "haven't", "having",
    "he", "he'd", "he'll", "he's", "her", "here", "here's", "hers", "herself",
    "him", "himself", "his", "how", "how's", "i", "i'd", "i'll", "i'm",
    "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself",
    "let's", "me", "more", "most", "mustn't", "my", "myself", "no", "nor",
    "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our",
    "ours", "ourselves", "out", "over", "own", "same", "shan't", "she",
    "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll",
    "they're", "they've", "this", "those", "through", "to", "too", "under",
    "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're",
    "we've", "were", "weren't", "what", "what's", "when", "when's", "where",
    "where's", "which", "while", "who", "who's", "whom", "why", "why's",
    "with", "won't", "would", "wouldn't", "you", "you'd", "you'll", "you're",
    "you've", "your", "yours", "yourself", "yourselves"
}

# ============================================================
# TRAP DETECTION
# ============================================================
# Track how many URLs we've seen per path pattern to detect traps
# (e.g., calendar pages that go on forever, or paginated results)
path_pattern_counts = defaultdict(int)
MAX_PATTERN_COUNT = 100  # If we see 100+ URLs with the same pattern, it's likely a trap

# Known trap patterns
TRAP_PATTERNS = [
    r'/calendar/',
    r'/events/',
    r'\?ical=',
    r'\?share=',
    r'\?replytocom=',
    r'/wp-json/',
    r'/wp-admin/',
    r'/wp-login',
    r'/feed/',
    r'/tag/',
    r'/page/\d+',
    r'/attachment/',
    r'action=login',
    r'action=download',
    r'do=hierarchyview',
    r'do=backlink',
    r'do=revisions',
    r'do=media',
    r'do=index',
    r'do=recent',
    r'do=diff',
    r'do=edit',
    r'do=export',
    r'version=',
    r'format=',
    r'tribe-bar-date=',
    r'ics_file=',
    r'/pdf/',
    r'\.pdf$',
    r'/slide_show/',
    r'gallery',
    r'login',
    r'mailto:',
    r'tel:',
    r'javascript:',
]

def get_path_pattern(url):
    """Convert a URL path into a pattern by replacing numbers with {N}.
    This helps detect trap patterns like /page/1, /page/2, /page/3..."""
    parsed = urlparse(url)
    # Replace sequences of digits with {N}
    pattern = re.sub(r'\d+', '{N}', parsed.path)
    return f"{parsed.netloc}{pattern}"


def save_stats():
    """Save current stats to a JSON file for the report."""
    try:
        stats = {
            "unique_pages_count": len(unique_pages),
            "longest_page": {
                "url": longest_page[0],
                "word_count": longest_page[1]
            },
            "top_50_words": sorted(word_counts.items(), key=lambda x: -x[1])[:50],
            "subdomains": {
                domain: {"count": len(urls), "sample_urls": list(urls)[:5]}
                for domain, urls in sorted(subdomain_pages.items())
            }
        }
        with open(STATS_FILE, 'w') as f:
            json.dump(stats, f, indent=2)
    except Exception as e:
        print(f"Error saving stats: {e}")


# ============================================================
# MAIN SCRAPER FUNCTION
# ============================================================
def scraper(url, resp):
    """
    Main scraper function called by the worker.
    
    Args:
        url: The URL that was downloaded
        resp: Response object with .status, .raw_response, .error, .url
    
    Returns:
        List of URLs (strings) extracted from this page
    """
    links = extract_next_links(url, resp)
    valid_links = [link for link in links if is_valid(link)]
    return valid_links


def extract_next_links(url, resp):
    """
    Parse the response, collect stats, and extract links.
    """
    global longest_page
    
    # ----------------------------------------------------------
    # 1. Check if response is usable
    # ----------------------------------------------------------
    # Only process 200 OK responses
    if resp.status != 200:
        return []
    
    # Check that we actually got content
    if not resp.raw_response or not resp.raw_response.content:
        return []
    
    # Check content type - only process HTML
    content_type = resp.raw_response.headers.get('Content-Type', '')
    if content_type and 'text/html' not in content_type:
        return []
    
    # Avoid very large pages (>10MB likely not useful text)
    if len(resp.raw_response.content) > 10 * 1024 * 1024:
        return []
    
    # ----------------------------------------------------------
    # 2. Parse the HTML
    # ----------------------------------------------------------
    try:
        soup = BeautifulSoup(resp.raw_response.content, 'lxml')
    except Exception:
        try:
            soup = BeautifulSoup(resp.raw_response.content, 'html.parser')
        except Exception:
            return []
    
    # ----------------------------------------------------------
    # 3. Extract text and check for low-information pages
    # ----------------------------------------------------------
    # Get visible text (not scripts, styles, etc.)
    # Only remove script/style — keep nav/header/footer since UCI pages
    # often have meaningful content there
    text_soup = BeautifulSoup(resp.raw_response.content, 'lxml')
    for tag in text_soup(['script', 'style', 'noscript']):
        tag.decompose()
    
    text = text_soup.get_text(separator=' ', strip=True)
    
    # Tokenize: split into words, keep only alphabetic tokens
    words = [w.lower() for w in re.findall(r'[a-zA-Z]+', text)]
    
    # Low information check: skip pages with very few words
    if len(words) < 25:
        # Still extract links from navigation-heavy pages, but don't count stats
        pass
    else:
        # ----------------------------------------------------------
        # 4. Collect statistics for the report
        # ----------------------------------------------------------
        # Defragment URL for uniqueness
        defragged_url = urldefrag(url)[0]
        unique_pages.add(defragged_url)
        
        # Track longest page
        if len(words) > longest_page[1]:
            longest_page = (defragged_url, len(words))
        
        # Count words (excluding stop words)
        for word in words:
            if word not in STOP_WORDS and len(word) > 1:
                word_counts[word] += 1
        
        # Track subdomains within *.ics.uci.edu
        parsed_url = urlparse(defragged_url)
        netloc = parsed_url.netloc.lower()
        # Record subdomain for any uci.edu domain
        subdomain_pages[netloc].add(defragged_url)
        
        # Periodically save stats (every 100 pages)
        if len(unique_pages) % 100 == 0:
            save_stats()
            print(f"[STATS] Unique pages so far: {len(unique_pages)}")
    
    # ----------------------------------------------------------
    # 5. Extract links
    # ----------------------------------------------------------
    links = []
    
    for anchor in soup.find_all('a', href=True):
        href = anchor['href'].strip()
        
        # Skip empty, javascript, mailto links
        if not href or href.startswith(('javascript:', 'mailto:', 'tel:', '#')):
            continue
        
        # Convert relative URLs to absolute
        absolute_url = urljoin(url, href)
        
        # Remove fragment
        defragged = urldefrag(absolute_url)[0]
        
        # Normalize: remove trailing slash for consistency
        if defragged.endswith('/'):
            defragged = defragged.rstrip('/')
        
        links.append(defragged)
    
    return links


# ============================================================
# URL VALIDATION
# ============================================================
def is_valid(url):
    """
    Decide whether to crawl this URL or not.
    
    Returns True if the URL should be crawled, False otherwise.
    """
    try:
        parsed = urlparse(url)
        
        # ----------------------------------------------------------
        # Scheme check
        # ----------------------------------------------------------
        if parsed.scheme not in {"http", "https"}:
            return False
        
        netloc = parsed.netloc.lower()
        path = parsed.path.lower()
        
        # ----------------------------------------------------------
        # Domain check: must be within allowed domains
        # ----------------------------------------------------------
        # List of websites to crawl:
        #   *.ics.uci.edu/*
        #   *.cs.uci.edu/*
        #   *.informatics.uci.edu/*
        #   *.stat.uci.edu/*
        
        allowed = False
        if (netloc == 'ics.uci.edu' or netloc.endswith('.ics.uci.edu')):
            allowed = True
        elif (netloc == 'cs.uci.edu' or netloc.endswith('.cs.uci.edu')):
            allowed = True
        elif (netloc == 'informatics.uci.edu' or netloc.endswith('.informatics.uci.edu')):
            allowed = True
        elif (netloc == 'stat.uci.edu' or netloc.endswith('.stat.uci.edu')):
            allowed = True
        
        if not allowed:
            return False
        
        # ----------------------------------------------------------
        # File extension check: avoid non-HTML files
        # ----------------------------------------------------------
        if re.match(
            r".*\.(css|js|bmp|gif|jpe?g|ico"
            + r"|png|tiff?|mid|mp2|mp3|mp4"
            + r"|wav|avi|mov|mpeg|ram|m4v|mkv|ogg|ogv|pdf"
            + r"|ps|eps|tex|ppt|pptx|doc|docx|xls|xlsx|names"
            + r"|data|dat|exe|bz2|tar|msi|bin|7z|psd|dmg|iso"
            + r"|epub|dll|cnf|tgz|sha1"
            + r"|thmx|mso|arff|rtf|jar|csv"
            + r"|rm|smil|wmv|swf|wma|zip|rar|gz"
            + r"|img|sql|db|bak|cfg|conf|ini|log"
            + r"|xml|json|rss|atom|svg|woff|woff2|ttf|eot"
            + r"|apk|war|mpg|php|asp|jsp|cgi|py|pl|sh|bat"
            + r"|r|m|cc|c|h|cpp|java|class|o)$", path):
            return False
        
        # ----------------------------------------------------------
        # Trap detection: known bad patterns
        # ----------------------------------------------------------
        full_url = url.lower()
        for pattern in TRAP_PATTERNS:
            if re.search(pattern, full_url):
                return False
        
        # ----------------------------------------------------------
        # Path depth check: very deep paths are often traps
        # ----------------------------------------------------------
        path_parts = [p for p in parsed.path.split('/') if p]
        if len(path_parts) > 15:
            return False
        
        # ----------------------------------------------------------
        # Query string check: too many parameters often indicates dynamic trap
        # ----------------------------------------------------------
        if parsed.query:
            params = parsed.query.split('&')
            if len(params) > 5:
                return False
        
        # ----------------------------------------------------------
        # Repeating path segments (trap indicator)
        # e.g., /a/b/a/b/a/b/
        # ----------------------------------------------------------
        if len(path_parts) >= 4:
            for i in range(len(path_parts) - 1):
                segment = path_parts[i]
                count = path_parts.count(segment)
                if count >= 3:
                    return False
        
        # ----------------------------------------------------------
        # Path pattern frequency check (detect infinite traps)
        # ----------------------------------------------------------
        pattern = get_path_pattern(url)
        path_pattern_counts[pattern] += 1
        if path_pattern_counts[pattern] > MAX_PATTERN_COUNT:
            return False
        
        # ----------------------------------------------------------
        # URL length check
        # ----------------------------------------------------------
        if len(url) > 300:
            return False
        
        return True

    except TypeError:
        print("TypeError for", url)
        return False