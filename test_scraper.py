#!/usr/bin/env python3
"""
LOCAL TEST SCRIPT for your crawler's scraper.
This lets you test scraper.py WITHOUT hitting the cache server.

It fetches pages directly from the web and feeds them to your scraper
as if the cache server had provided them.

Usage:
    python3 test_scraper.py

What it does:
1. Fetches each seed URL directly
2. Passes the response to your scraper function
3. Shows you what links were extracted
4. Follows links for a few levels (configurable)
"""

import requests
import re
from urllib.parse import urlparse, urldefrag
from collections import defaultdict

# ============================================================
# MOCK RESPONSE CLASS
# Mimics the Response object your scraper expects
# ============================================================
class MockRawResponse:
    def __init__(self, response):
        self.content = response.content
        self.headers = dict(response.headers)
        self.url = response.url

class MockResponse:
    def __init__(self, url, requests_response):
        self.url = url
        self.status = requests_response.status_code
        self.error = None
        self.raw_response = MockRawResponse(requests_response)


# ============================================================
# IMPORT YOUR SCRAPER
# ============================================================
import scraper as scraper_module
from scraper import scraper, is_valid, unique_pages, word_counts, subdomain_pages, save_stats


def test_single_url(url):
    """Test the scraper on a single URL and show results."""
    print(f"\n{'='*70}")
    print(f"TESTING: {url}")
    print(f"{'='*70}")
    
    try:
        resp = requests.get(url, timeout=10, 
                          headers={'User-Agent': 'Mozilla/5.0 (Test Crawler)'})
        mock_resp = MockResponse(url, resp)
        
        print(f"  Status: {resp.status_code}")
        print(f"  Content-Type: {resp.headers.get('Content-Type', 'unknown')}")
        print(f"  Content Length: {len(resp.content)} bytes")
        
        links = scraper(url, mock_resp)
        
        print(f"\n  Links extracted: {len(links)}")
        
        # Show first 20 links
        for i, link in enumerate(links[:20]):
            print(f"    [{i+1}] {link}")
        if len(links) > 20:
            print(f"    ... and {len(links) - 20} more")
        
        # Show domain distribution
        domains = defaultdict(int)
        for link in links:
            parsed = urlparse(link)
            domains[parsed.netloc] += 1
        
        print(f"\n  Domains found in links:")
        for domain, count in sorted(domains.items(), key=lambda x: -x[1]):
            print(f"    {domain}: {count} links")
        
        return links
        
    except Exception as e:
        print(f"  ERROR: {e}")
        return []


def test_is_valid():
    """Test the is_valid function with various URLs."""
    print("\n" + "="*70)
    print("TESTING is_valid() function")
    print("="*70)
    
    test_urls = [
        # Should be VALID
        ("https://www.ics.uci.edu", True),
        ("https://www.cs.uci.edu", True),
        ("https://www.informatics.uci.edu", True),
        ("https://www.stat.uci.edu", True),
        ("https://ics.uci.edu", True),
        ("https://cs.uci.edu", True),
        ("https://ngs.ics.uci.edu/something", True),
        ("https://vision.ics.uci.edu/demo", True),
        ("http://www.ics.uci.edu/~welling", True),
        ("https://www.stat.uci.edu/faculty", True),
        ("https://emj.ics.uci.edu/category/news", True),
        
        # Should be INVALID - wrong domain
        ("https://www.uci.edu", False),
        ("https://www.eng.uci.edu", False),
        ("https://google.com", False),
        ("https://www.math.uci.edu", False),
        
        # Should be INVALID - bad file types
        ("https://www.ics.uci.edu/file.pdf", False),
        ("https://www.ics.uci.edu/image.png", False),
        ("https://www.ics.uci.edu/style.css", False),
        
        # Should be INVALID - traps
        ("https://www.ics.uci.edu/calendar/2024", False),
        ("https://www.ics.uci.edu/wp-admin/post", False),
    ]
    
    all_passed = True
    for url, expected in test_urls:
        result = is_valid(url)
        status = "✓" if result == expected else "✗ FAIL"
        if result != expected:
            all_passed = False
        print(f"  {status}  is_valid({url}) = {result} (expected {expected})")
    
    if all_passed:
        print("\n  All tests passed! ✓")
    else:
        print("\n  Some tests FAILED! Fix is_valid() before running the real crawler.")


def mini_crawl(seed_urls, max_pages=30):
    """
    Do a small crawl starting from seed URLs.
    This simulates what the real crawler does, but only visits max_pages.
    """
    print("\n" + "="*70)
    print(f"MINI CRAWL (max {max_pages} pages)")
    print("="*70)
    
    visited = set()
    to_visit = list(seed_urls)
    all_links_found = 0
    
    while to_visit and len(visited) < max_pages:
        url = to_visit.pop(0)
        
        defragged = urldefrag(url)[0]
        if defragged in visited:
            continue
        visited.add(defragged)
        
        print(f"\n[{len(visited)}/{max_pages}] Crawling: {url}")
        
        try:
            resp = requests.get(url, timeout=10,
                              headers={'User-Agent': 'Mozilla/5.0 (Test Crawler)'})
            mock_resp = MockResponse(url, resp)
            
            links = scraper(url, mock_resp)
            all_links_found += len(links)
            
            print(f"  Status: {resp.status_code}, Links found: {len(links)}")
            
            # Add new links to visit
            for link in links:
                if urldefrag(link)[0] not in visited:
                    to_visit.append(link)
            
        except Exception as e:
            print(f"  ERROR: {e}")
    
    # Print summary
    print(f"\n{'='*70}")
    print("CRAWL SUMMARY")
    print(f"{'='*70}")
    print(f"  Pages visited: {len(visited)}")
    print(f"  Total links found: {all_links_found}")
    print(f"  URLs still in queue: {len(to_visit)}")
    print(f"  Unique pages (with content): {len(unique_pages)}")
    print(f"  Longest page: {scraper_module.longest_page[0]} ({scraper_module.longest_page[1]} words)")
    
    print(f"\n  Subdomains found:")
    for domain in sorted(subdomain_pages.keys()):
        print(f"    {domain}: {len(subdomain_pages[domain])} pages")
    
    print(f"\n  Top 20 words:")
    top_words = sorted(word_counts.items(), key=lambda x: -x[1])[:20]
    for word, count in top_words:
        print(f"    {word}: {count}")
    
    # Save stats
    save_stats()
    print(f"\n  Stats saved to crawl_stats.json")


if __name__ == "__main__":
    print("="*70)
    print("SCRAPER LOCAL TEST SUITE")
    print("="*70)
    
    # Test 1: Validate URL filtering
    test_is_valid()
    
    # Test 2: Test scraper on each seed URL individually
    seed_urls = [
        "https://www.ics.uci.edu",
        "https://www.cs.uci.edu",
        "https://www.informatics.uci.edu",
        "https://www.stat.uci.edu",
    ]
    
    all_links = []
    for url in seed_urls:
        links = test_single_url(url)
        all_links.extend(links)
    
    print(f"\n{'='*70}")
    print(f"TOTAL links from all seeds: {len(all_links)}")
    print(f"UNIQUE links: {len(set(all_links))}")
    print(f"{'='*70}")
    
    # Test 3: Mini crawl - follow links for a few pages
    print("\nDo you want to run a mini crawl? (visits ~30 pages)")
    choice = input("Enter 'y' to run, anything else to skip: ").strip().lower()
    if choice == 'y':
        mini_crawl(seed_urls, max_pages=30)