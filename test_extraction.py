import re
import json
import base64

def _xor_dec(data, key):
    return "".join(chr(c ^ key) for c in data)

def check_decoy(url, page_url):
    if not url: return True
    if ('wikisport.club' in page_url or 'stellarthread.com' in page_url) and '/hls/stream.m3u8?ch=' in url:
        return True
    return False

def _find_m3u8(html, page_url=''):
    # Heuristic 1: Look for character array joins like ["h","t","t","p", ...].join("")
    # Enhanced to handle leading parenthesis and more variants
    for join_match in re.finditer(r'\(?(\[\s*(?:["\'](?:\\.|[^"\'])+?["\']\s*,\s*)*["\'](?:\\.|[^"\'])+?["\']\s*\])\s*\.join\s*\(\s*["\']["\']\s*\)', html):
        try:
            array_content = join_match.group(1)
            chars = re.findall(r'["\']((?:\\.|[^"\'])+?)["\']', array_content)
            joined = "".join(chars).replace('\\/', '/').replace('\\', '')
            if '.m3u8' in joined:
                start_pos = join_match.end()
                suffix = ""
                # Look for additions
                for part_match in re.finditer(r'\s*\+\s*(?:["\']([^"\']*)["\']|\w+\.innerHTML|(\w+)\.join\(["\']["\']\)|\w+(?!\()|document\.getElementById\(["\'](\w+)["\']\)\.innerHTML)', html[start_pos:start_pos+500]):
                    if part_match.group(1): suffix += part_match.group(1)
                    elif part_match.group(3):
                        elem_m = re.search(r'id\s*=\s*["\']?' + part_match.group(3) + r'["\']?[^>]*>([^<]*)', html)
                        if elem_m: suffix += elem_m.group(1).strip()
                url = joined + suffix
                if not check_decoy(url, page_url):
                    return url
        except: continue

    # Heuristic 2: base64
    for b64_match in re.finditer(r'["\']([A-Za-z0-9+/=]{20,})["\']', html):
        try:
            decoded = base64.b64decode(b64_match.group(1)).decode('utf-8', 'ignore')
            if '.m3u8' in decoded:
                m3u8_url_m = re.search(r'(https?://[^"\'\s]+\.m3u8[^"\'\s]*|/[^"\'\s]+\.m3u8[^"\'\s]*)', decoded)
                if m3u8_url_m:
                    url = m3u8_url_m.group(0)
                    if not check_decoy(url, page_url):
                        return url
        except: continue
        
    return "NOT_FOUND"

with open('debug_t9.html', 'r', encoding='utf-8') as f:
    html = f.read()

print("Testing find_m3u8 on debug_t9.html...")
print("Result:", _find_m3u8(html, 'https://stellarthread.com/wiki.php'))
