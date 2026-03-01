# resolver.py — Stream URL resolution for plugin.video.livetvsxsports
#
# Confirmed resolution chain (from live page analysis):
#
#   CDN webplayer page (webplayer2.php?t=alieztv or webplayer.php?t=ifr)
#     → contains an <iframe> to an external player e.g. emb.apl390.me/player/live.php?id=XXXXX
#       → that player page contains:
#           pl.init('//a74.azplay26.me/hls/streamaXXXXX/index.m3u8?cst=TOKEN');
#         OR just a plain m3u8 URL in the HTML
#
# Strategy:
#   1. Fetch the CDN webplayer page
#   2. Find the iframe pointing to the real player (skip ads/banners)
#   3. Fetch that player iframe page
#   4. Extract the m3u8 URL from pl.init(...) or any other m3u8 reference
#   5. Fall back to the raw iframe URL if no m3u8 is found

import re
import base64
import json
import time
import urllib.parse
import requests
import urllib3
import ssl
from requests.adapters import HTTPAdapter
from resources.lib.utils import log, USER_AGENT, get_base_url, get_setting

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class SSLAdapter(HTTPAdapter):
    """Custom adapter to fix SSLEOFError by forcing modern TLS configuration."""
    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context()
        # Some servers close connection on EOF violation if certain ciphers are used
        # We try to be as permissive as possible for the handshake phase
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = context
        return super(SSLAdapter, self).init_poolmanager(*args, **kwargs)

SESSION = requests.Session()
SESSION.mount('https://', SSLAdapter())
SESSION.headers.update({
    'User-Agent': USER_AGENT,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
})

# Ad/tracker domains to skip when filtering iframes
_AD_DOMAINS = ('ads.', 'ad.', 'banner', 'tracker', 'analytics', 'googletagmanager',
               'doubleclick', 'facebook.com', 'twitter.com', 'getbanner')


def _get(url, referer=None, timeout=8):
    """Internal helper for making requests with browser headers."""
    try:
        headers = {'Referer': referer} if referer else {}
        r = SESSION.get(url, headers=headers, timeout=timeout, verify=False)
        return r.url, r.text
    except Exception as e:
        log('Resolver GET failed: {} — {}'.format(url, str(e)), 'error')
        return url, ''


def _abs(url, base=''):
    """Make a protocol-relative or path-relative URL absolute."""
    url = url.strip().replace('\r', '').replace('\n', '')
    if url.startswith('http'):
        return url
    if url.startswith('//'):
        return 'https:' + url
    if url.startswith('/') and base:
        from urllib.parse import urlparse
        parsed = urlparse(base)
        return '{}://{}{}'.format(parsed.scheme, parsed.netloc, url)
    return url


def _xor_dec(data, key):
    """Python implementation of the viewembed XOR decoder."""
    try:
        if isinstance(data, str):
            data = json.loads(data)
        return "".join(chr(c ^ key) for c in data)
    except Exception as e:
        log('XOR decode failed: ' + str(e), 'debug')
        return ""

def _find_m3u8(html, page_url=''):
    """
    Search for HLS m3u8 stream URLs in a page using various generic patterns.
    """
    if not html:
        return None


    patterns = [
        # pl.init('//host/path/index.m3u8?token')
        r"pl\.init\s*\(\s*['\"]([^'\"]+\.m3u8[^'\"]*)['\"]",
        # Generic http(s) m3u8
        r'["\']?(https?://[^"\'<>\s]+\.m3u8[^"\'<>\s]*)',
        # Protocol-relative // m3u8
        r'["\']?(//[^"\'<>\s]+\.m3u8[^"\'<>\s]*)',
        # jwplayer / videojs / fluidplayer config
        r'["\']file["\']\s*:\s*["\']([^"\']+\.m3u8[^"\']*)',
        r'src\s*[=:]\s*["\']([^"\']+\.m3u8[^"\']*)',
        r'hls\.loadSource\s*\(\s*["\']([^"\']+)'
    ]
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            url = _abs(m.group(1).strip("\"'").split('\\')[0], page_url)
            if url and not _is_decoy(url, page_url):
                log('Found m3u8 via pattern: ' + url, 'debug')
                return url

    # Heuristic 1: Look for character array joins like ["h","t","t","p", ...].join("")
    # These are usually the real high-protection streams (e.g. stellarthread)
    for join_match in re.finditer(r'\(?(\[\s*(?:["\'](?:\\.|[^"\'])+?["\']\s*,\s*)*["\'](?:\\.|[^"\'])+?["\']\s*\])\s*\.join\s*\(\s*["\']["\']\s*\)', html):
        try:
            array_content = join_match.group(1)
            chars = re.findall(r'["\']((?:\\.|[^"\'])+?)["\']', array_content)
            joined = "".join(chars).replace('\\/', '/').replace('\\', '')
            if '.m3u8' in joined:
                start_pos = join_match.end()
                suffix = ""
                # Look for simple additions after the join, searching further for document elements
                for part_match in re.finditer(r'\s*\+\s*(?:["\']([^"\']*)["\']|\w+\.innerHTML|(\w+)(?!\()|document\.getElementById\(["\'](\w+)["\']\)\.innerHTML)', html[start_pos:start_pos+500]):
                    if part_match.group(1): suffix += part_match.group(1)
                    elif part_match.group(3):
                        elem_id = part_match.group(3)
                        elem_m = re.search(r'id\s*=\s*["\']?' + elem_id + r'["\']?[^>]*>([^<]*)', html)
                        if elem_m: 
                            content = elem_m.group(1).strip()
                            log('Found dynamic suffix in element {}: {}'.format(elem_id, content), 'debug')
                            suffix += content
                url = _abs(joined + suffix, page_url)
                if url and not _is_decoy(url, page_url):
                    log('Found m3u8 in character array join (+suffix): ' + url, 'debug')
                    return url
        except: continue

    # Heuristic 2: Look for any base64 encoded strings that might contain .m3u8
    for b64_match in re.finditer(r'["\']([A-Za-z0-9+/=]{20,})["\']', html):
        try:
            val = b64_match.group(1)
            decoded = base64.b64decode(val).decode('utf-8', 'ignore')
            if '.m3u8' in decoded:
                m3u8_url_m = re.search(r'(https?://[^"\'\s]+\.m3u8[^"\'\s]*|/[^"\'\s]+\.m3u8[^"\'\s]*)', decoded)
                if m3u8_url_m:
                    url = _abs(m3u8_url_m.group(0), page_url)
                    if not _is_decoy(url, page_url):
                        log('Found m3u8 in base64 string: ' + url, 'debug')
                        return url
        except: continue

    # Heuristic 3: XOR
    try:
        arrays = {}
        for m in re.finditer(r'(_init_[a-f0-9]{8,}|var\s+\w+)\s*=\s*(\[[0-9,\s]+\])', html):
            name = m.group(1).split()[-1]
            arrays[name] = json.loads(m.group(2))
        
        for m in re.finditer(r'(\w+)\s*\(\s*(\w+)\s*,\s*(\d+)\s*\)', html):
            key = int(m.group(3))
            if m.group(2) in arrays:
                decoded = _xor_dec(arrays[m.group(2)], key)
                if '.m3u8' in decoded:
                    url = _abs(decoded, page_url)
                    if not _is_decoy(url, page_url):
                        log('Found m3u8 in XOR: ' + url, 'debug')
                        return url
    except Exception: pass

    return None


def _find_player_iframes(html, page_url=''):
    """
    Return a list of non-ad iframe src URLs from the page.
    Cleans up protocol-relative and relative paths.
    """
    srcs = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
    result = []
    for src in srcs:
        src = src.strip().replace('\r', '').replace('\n', '').replace(' ', '')
        if any(skip in src for skip in _AD_DOMAINS):
            continue
        abs_src = _abs(src, page_url)
        if abs_src:
            result.append(abs_src)
    return result


def _resolve_recursive(url, referer=None, depth=0):
    """
    Recursively search for a playable stream through iframes.
    """
    if depth > 3: # Avoid deep recursion
        return None

    log('Deep resolving (level {}): {}'.format(depth, url))
    final_url, html = _get(url, referer=referer)
    if not html:
        return None

    # Step 1: Specific high-fidelity scrapers for known complex sites
    
    # Wikisport / Stellarthread (Tennis)
    if 'stellarthread.com' in final_url or 'wikisport.club' in final_url or re.search(r'fid\s*=\s*["\']([^"\']+)["\']', html):
        fid_m = re.search(r'fid\s*=\s*["\']([^"\']+)["\']', html)
        if fid_m:
            fid = fid_m.group(1)
            wiki_url = 'https://stellarthread.com/wiki.php?player=desktop&live=' + fid
            if wiki_url != url:
                log('Recursing to stellarthread player: ' + wiki_url)
                res = _resolve_recursive(wiki_url, referer=final_url, depth=depth+1)
                if res: return res

        # If on the player page, use the character array join + span reconstruction
        # Look for the .m3u8 join logic specifically
        chars_m = re.search(r'(\[\s*(?:["\'](?:\\.|[^"\'])+?["\']\s*,\s*)*["\'](?:\\.|[^"\'])+?["\']\s*\])\s*\.join\s*\(\s*["\']["\']\s*\)', html)
        if chars_m:
            try:
                chars = re.findall(r'["\']((?:\\.|[^"\'])+?)["\']', chars_m.group(1))
                base = "".join(chars).replace('\\/', '/')
                if '.m3u8' in base:
                    # Look for innerHTML appends (the MD5/token)
                    suffix = ""
                    for span_m in re.finditer(r'document\.getElementById\(["\'](\w+)["\']\)\.innerHTML', html):
                        span_id = span_m.group(1)
                        content_m = re.search(r'id\s*=\s*["\']?' + span_id + r'["\']?[^>]*>([^<]*)', html)
                        if content_m: suffix += content_m.group(1).strip()
                    url = base + suffix
                    if not _is_decoy(url, final_url):
                        log('Stellarthread stream resolved: ' + url)
                        return '{}|Referer={}'.format(url, urllib.parse.quote(final_url))
            except: pass

    # Viewembed (Volleyball/Cricket)
    if 'viewembed.ru' in final_url or re.search(r'_dec_[a-f0-9]{8}', html):
        log('Attempting Viewembed specific resolution...')
        try:
            # XOR Decode Parameters
            arrays = {}
            for m in re.finditer(r'(_init_[a-f0-9]{8,})\s*=\s*(\[[^\]]+\])', html):
                arrays[m.group(1)] = json.loads(m.group(2))
            
            resolved = {}
            for m in re.finditer(r'(_dec_[a-f0-9]{8}|\w+)\((_init_[a-f0-9]{8,}),\s*(\d+)\)', html):
                array_name, key = m.group(2), int(m.group(3))
                if array_name in arrays:
                    val = _xor_dec(arrays[array_name], key)
                    if val: resolved[array_name] = val
            
            cid = next((v for v in resolved.values() if 5 < len(v) < 25 and not v.startswith('http')), "")
            
            if cid:
                # 1. Try old get_stream API FIRST (Usually cleaner/direct m3u8)
                token = next((v for v in resolved.values() if len(v) > 40), "")
                if token:
                    api = 'https://viewembed.ru/get_stream?id={}&token={}&t={}'.format(cid, token, int(time.time()))
                    log('Attempting Viewembed get_stream API: ' + api)
                    _, api_text = _get(api, referer=final_url, timeout=10)
                    m_m = re.search(r'https?://[^"\'\s]+\.m3u8[^"\'\s]*', api_text)
                    if m_m:
                        log('Resolved via get_stream API: ' + m_m.group(0))
                        return '{}|Referer={}'.format(m_m.group(0).replace('\\/', '/'), urllib.parse.quote(final_url))

                # 2. Try server_lookup (Fallback / PNG Disguise)
                lookup_m = re.search(r'["\'](https?://[^"\'\s]+/server_lookup[^"\'\s]*)["\']', html)
                if lookup_m:
                    l_url = lookup_m.group(1).split('?')[0] + '?channel_id=' + cid
                    _, l_text = _get(l_url, referer=final_url, timeout=10)
                    try:
                        sk = json.loads(l_text).get('server_key')
                        if sk:
                            log('Viewembed Server Key: ' + sk)
                            # Pick the right template
                            templates = re.findall(r'[`"\'\s](https?://[^`"\'\s]+/proxy/[^`"\'\s]+)[`"\'\s]', html)
                            for tmpl in templates:
                                if '${sk}' in tmpl or sk in tmpl:
                                    res_url = tmpl.replace('${sk}', sk).replace('${CHANNEL_KEY}', cid).replace('`', '')
                                    # CRITICAL: Force MimeType to avoid Kodi misidentifying .css/.png as images
                                    res_url += '|MimeType=application/vnd.apple.mpegurl'
                                    log('Resolved via server_lookup (forced HLS): ' + res_url)
                                    return '{}|Referer={}'.format(res_url, urllib.parse.quote(final_url))
                    except: pass
        except Exception as e:
            log('Viewembed error: ' + str(e), 'debug')

    # Step 2: Generic Heuristics (for other sites)
    m3u8 = _find_m3u8(html, final_url)
    if m3u8:
        return '{}|Referer={}'.format(m3u8, urllib.parse.quote(final_url))

    # Step 3: Follow Iframes
    iframes = _find_player_iframes(html, final_url)
    for ifr_url in iframes:
        if ifr_url == url: continue
        res = _resolve_recursive(ifr_url, referer=final_url, depth=depth+1)
        if res: return res

    return None

def _is_decoy(url, page_url=''):
    """Helper to catch fake stream URLs used by protection scripts."""
    if not url: return True
    # Wikisport/Stellarthread fake link
    if ('wikisport.club' in page_url or 'stellarthread.com' in page_url) and '/hls/stream.m3u8?ch=' in url:
        return True
    return False

def resolve_stream(player_url, event_id=None):
    """
    Resolve a CDN webplayer URL to an actual playable m3u8 stream URL.
    """
    if not player_url:
        return None

    log('Starting Universal Resolution: ' + player_url)

    # Initial fetch to get the ball rolling
    res = _resolve_recursive(player_url, referer=get_base_url() + '/enx/')
    
    if res:
        return res

    # Fallback to the original URL if everything fails (Kodi might handle it)
    log('Universal resolver failed to find m3u8, falling back to original URL', 'warning')
    return player_url


def resolve_highlight(base_url, video_url):
    """
    Resolve a highlight/video archive page to a playable URL.
    These pages at /enx/showvideo/{id}/ usually embed a YouTube iframe.
    """
    full_url = base_url + video_url
    _, html = _get(full_url, referer=base_url + '/enx/video/')
    if not html:
        return None

    m3u8 = _find_m3u8(html)
    if m3u8:
        return m3u8

    iframes = _find_player_iframes(html, full_url)
    if iframes:
        log('Highlight iframe: ' + iframes[0])
        return iframes[0]

    return None
