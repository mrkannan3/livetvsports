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
import urllib.parse
import requests
import urllib3
from resources.lib.utils import log, USER_AGENT, get_base_url, get_setting

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': USER_AGENT,
    'Accept-Language': 'en-US,en;q=0.9',
})

# Ad/tracker domains to skip when filtering iframes
_AD_DOMAINS = ('ads.', 'ad.', 'banner', 'tracker', 'analytics', 'googletagmanager',
               'doubleclick', 'facebook.com', 'twitter.com', 'getbanner')


def _get(url, referer=None):
    """GET request → (final_url, text). Never raises."""
    headers = {'User-Agent': USER_AGENT}
    if referer:
        headers['Referer'] = referer
    try:
        r = SESSION.get(url, headers=headers, timeout=15,
                        allow_redirects=True, verify=False)
        return r.url, r.text
    except Exception as e:
        log('Resolver GET failed: {} — {}'.format(url, e), 'error')
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


def _find_m3u8(html):
    """
    Search for HLS m3u8 stream URLs in a page.
    Handles both http:// and protocol-relative // prefixes.
    Also checks pl.init(...) calls used by the apl390.me player.
    """
    patterns = [
        # pl.init('//host/path/index.m3u8?token')  — the confirmed pattern
        r"pl\.init\s*\(\s*['\"]([^'\"]+\.m3u8[^'\"]*)['\"]",
        # Generic http(s) m3u8
        r'["\']?(https?://[^"\'<>\s]+\.m3u8[^"\'<>\s]*)',
        # Protocol-relative // m3u8
        r'["\']?(//[^"\'<>\s]+\.m3u8[^"\'<>\s]*)',
        # jwplayer / videojs file config
        r'["\']file["\']\s*:\s*["\']([^"\']+\.m3u8[^"\']*)',
        r'src\s*[=:]\s*["\']([^"\']+\.m3u8[^"\']*)',
        r'hls\.loadSource\s*\(\s*["\']([^"\']+)',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            url = _abs(m.group(1).strip("\"'").split('\\')[0])
            if url:
                log('Found m3u8: ' + url, 'debug')
                return url

    # specialized check for base64 'mustave' variable (wikisport.club pattern)
    m = re.search(r"mustave\s*=\s*['\"]([^'\"]+)['\"]", html)
    if m:
        try:
            path = base64.b64decode(m.group(1)).decode('utf-8')
            if '.m3u8' in path:
                log('Found mustave base64 path: ' + path, 'debug')
                return path
        except Exception as e:
            log('Base64 decode failed: ' + str(e), 'debug')

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


def resolve_stream(player_url, event_id=None):
    """
    Resolve a CDN webplayer URL to an actual playable m3u8 stream URL.

    Args:
        player_url: The direct CDN webplayer URL
                    (e.g. https://cdn.livetv873.me/webplayer2.php?t=alieztv&c=242305...)
        event_id:   Optional event ID, used for logging only.

    Returns:
        str — playable m3u8 URL (or best available URL)
        None — if resolution failed completely
    """
    if not player_url:
        return None

    log('Resolving CDN player: ' + player_url)

    # --- Step 1: Fetch the CDN webplayer page ---
    cdn_url, cdn_html = _get(player_url, referer=get_base_url() + '/enx/')
    if not cdn_html:
        log('CDN webplayer page returned empty', 'warning')
        return player_url  # fall back to returning the CDN URL itself

    # Check for m3u8 directly in CDN page (rare but possible)
    m3u8 = _find_m3u8(cdn_html)
    if m3u8:
        log('m3u8 found directly in CDN webplayer page')
        return m3u8

    # --- Step 2: Find the player iframe (skip ads) ---
    iframes = _find_player_iframes(cdn_html, cdn_url)
    log('Player iframes found: {}'.format(iframes), 'debug')

    for iframe_url in iframes:
        log('Following player iframe: ' + iframe_url)
        final_url, iframe_html = _get(iframe_url, referer=cdn_url)
        if not iframe_html:
            continue

        # --- Step 3: Extract m3u8 from the player iframe page ---
        m3u8 = _find_m3u8(iframe_html)
        if m3u8:
            full_m3u8 = _abs(m3u8, final_url)
            log('m3u8 found in player iframe: ' + full_m3u8)
            # Add Referer for Kodi playback
            return '{}|Referer={}'.format(full_m3u8, urllib.parse.quote(final_url))

        # Specialized: wikisport.club dynamic iframe pattern
        # Initial page has fid="...", loads wiki.js which writes iframe to stellarthread.com/wiki.php
        fid_m = re.search(r'fid\s*=\s*["\']([^"\']+)["\']', iframe_html)
        if fid_m and 'stellarthread.com' in iframe_html:
            wiki_url = 'https://stellarthread.com/wiki.php?player=desktop&live=' + fid_m.group(1)
            log('Constructed wikisport helper URL: ' + wiki_url)
            final_wiki_url, wiki_html = _get(wiki_url, referer=iframe_url)
            m3u8 = _find_m3u8(wiki_html)
            if m3u8:
                full_m3u8 = _abs(m3u8, final_wiki_url)
                log('m3u8 found via wikisport helper: ' + full_m3u8)
                return '{}|Referer={}'.format(full_m3u8, urllib.parse.quote(final_wiki_url))

        # --- Step 4: One more level — nested iframes ---
        nested = _find_player_iframes(iframe_html, final_url)
        for nested_url in nested:
            log('Following nested iframe: ' + nested_url)
            final_nested_url, nested_html = _get(nested_url, referer=final_url)
            if not nested_html:
                continue
            m3u8 = _find_m3u8(nested_html)
            if m3u8:
                full_m3u8 = _abs(m3u8, final_nested_url)
                log('m3u8 found in nested iframe: ' + full_m3u8)
                return '{}|Referer={}'.format(full_m3u8, urllib.parse.quote(final_nested_url))

        # No m3u8 found in this iframe chain — try the iframe URL directly
        if iframe_html:
            log('Falling back to iframe URL: ' + str(iframe_url))
            return iframe_url

    # --- Last resort: return the CDN webplayer URL ---
    log('Could not extract m3u8 — returning CDN player URL: ' + player_url, 'warning')
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
