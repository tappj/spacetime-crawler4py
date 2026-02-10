import re
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

def scraper(url, resp):
    links = extract_next_links(url, resp)
    return [link for link in links if is_valid(link)]

def extract_next_links(url, resp):
    # Check if response is valid
    if resp.status != 200:
        return []
    
    if not resp.raw_response or not resp.raw_response.content:
        return []
    
    # Parse HTML
    try:
        soup = BeautifulSoup(resp.raw_response.content, 'html.parser')
        links = []
        
        # Extract all links
        for anchor in soup.find_all('a', href=True):
            link = urljoin(url, anchor['href'])
            # Remove fragment
            link = urlparse(link)._replace(fragment='').geturl()
            links.append(link)
        
        return links
    except:
        return []

def is_valid(url):
    try:
        parsed = urlparse(url)
        
        # Must be http or https
        if parsed.scheme not in {"http", "https"}:
            return False
        
        # Must be in allowed domains
        if not (parsed.netloc.endswith('.ics.uci.edu') or 
                parsed.netloc.endswith('.cs.uci.edu') or
                parsed.netloc.endswith('.informatics.uci.edu') or
                parsed.netloc.endswith('.stat.uci.edu') or
                parsed.netloc in {'ics.uci.edu', 'cs.uci.edu', 
                                  'informatics.uci.edu', 'stat.uci.edu'}):
            return False
        
        # Avoid non-HTML files
        return not re.match(
            r".*\.(css|js|bmp|gif|jpe?g|ico"
            + r"|png|tiff?|mid|mp2|mp3|mp4"
            + r"|wav|avi|mov|mpeg|ram|m4v|mkv|ogg|ogv|pdf"
            + r"|ps|eps|tex|ppt|pptx|doc|docx|xls|xlsx|names"
            + r"|data|dat|exe|bz2|tar|msi|bin|7z|psd|dmg|iso"
            + r"|epub|dll|cnf|tgz|sha1"
            + r"|thmx|mso|arff|rtf|jar|csv"
            + r"|rm|smil|wmv|swf|wma|zip|rar|gz)$", parsed.path.lower())

    except TypeError:
        print("TypeError for", parsed)
        return False