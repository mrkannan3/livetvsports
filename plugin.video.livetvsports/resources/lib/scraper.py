# scraper.py — HTTP requests and HTML parsing for livetv.sx pages

import re
import requests
import urllib3
from resources.lib.utils import log, USER_AGENT

# Suppress SSL warnings — livetv.sx cert is not trusted by Windows Python by default
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


SESSION = requests.Session()
SESSION.headers.update({'User-Agent': USER_AGENT})


def _get(url, referer=None):
    """Perform a GET request with appropriate headers."""
    headers = {'User-Agent': USER_AGENT}
    if referer:
        headers['Referer'] = referer
    log('GET: ' + url, 'debug')
    try:
        resp = SESSION.get(url, headers=headers, timeout=15, verify=False)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        log('Request failed: {} — {}'.format(url, str(e)), 'error')
        return ''


# ---------------------------------------------------------------------------
# Detect the current active CDN domain from the main page
# The sidebar always shows: "Method 1: new domain livetv873.me"
# ---------------------------------------------------------------------------
def get_cdn_domain(base_url):
    """Scrape the current CDN/mirror domain from the main page sidebar."""
    html = _get(base_url + '/enx/')
    # Looks for: livetv873.me  or  livetv765.me  etc.
    match = re.search(r'new domain[^>]*>\s*(livetv\d+\.me)', html, re.IGNORECASE)
    if match:
        domain = match.group(1)
        log('Detected CDN domain: ' + domain)
        return domain
    return 'livetv873.me'  # safe fallback


# ---------------------------------------------------------------------------
# Event list scraping
# Page: /enx/allupcomingsports/{sport_id}/  or  /enx/allupcoming/
# Each event row:
#   <a class="live" href="/enx/eventinfo/341302271_toulouse_paris/">
#     <b>Toulouse – Paris</b>  [LIVE icon if live]
#   </a>
#   <span class="evdesc"> (France. Ligue 1)</span>
#   time is in the adjacent <td> cell: "21:00"
# ---------------------------------------------------------------------------
EVENT_PATTERN = re.compile(
    r'<a\s[^>]*class="live"[^>]*href="/enx/eventinfo/(\d+)_([^/"]+)/"[^>]*>'
    r'(.*?)</a>'                      # group 3 = inner HTML (has team names + maybe LIVE icon)
    r'(?:.*?<span class="evdesc">(.*?)</span>)?',  # group 4 = league description e.g. "(France. Ligue 1)"
    re.DOTALL
)
# Date section header: <td colspan=4 height=48><br><b>22 February, Sunday</b><hr></td>
DATE_HEADER_PATTERN = re.compile(
    r'<td[^>]*colspan=["\']?4["\']?[^>]*height=["\']?48["\']?[^>]*>'  # the colspan=4 height=48 td
    r'.*?<b>([^<]+)</b>',
    re.DOTALL
)
TIME_PATTERN = re.compile(r'(\d{1,2}:\d{2})')
LIVE_IMG_PATTERN = re.compile(r'live\.gif', re.IGNORECASE)
TEAM_STRIP_PATTERN = re.compile(r'<[^>]+>')


def scrape_events(url):
    """
    Scrape a list of events from a sport category or all-upcoming page.

    Returns a list of dicts. Each item is either:

    A date-header separator:
      {
        'is_date_header': True,
        'date': str,          # e.g. "22 February, Sunday"
      }

    Or an event:
      {
        'is_date_header': False,  # or key absent
        'event_id': str,
        'slug': str,
        'name': str,
        'league': str,
        'time': str,
        'is_live': bool,
        'url': str,
      }
    """
    html = _get(url)
    if not html:
        return []

    # IMPORTANT: The page contains a left sidebar with ALL sports listed as
    # "cached sports" for the navigation widget.  We must restrict parsing to
    # the class="main" content area which is actually sport-filtered by the
    # server.  Without this restriction every sport page shows all events.
    main_pos = html.find('class="main"')
    if main_pos >= 0:
        html = html[main_pos:]
    else:
        content_pos = html.find('id="upcoming_main"')
        if content_pos >= 0:
            html = html[content_pos:]

    EVDESC_TIME = re.compile(r'(\d{1,2}):(\d{2})')  # groups: hour, minute
    EVDESC_DATETIME = re.compile(r'(\d{1,2}\s+\w+\s+at\s+\d{1,2}:\d{2})', re.IGNORECASE)  # "22 February at 14:30"
    EVDESC_LEAGUE = re.compile(r'\((.+)\)\s*$')

    # Build a combined iterator: find date headers and events in document order
    # by comparing match positions.
    date_iter = DATE_HEADER_PATTERN.finditer(html)
    event_iter = EVENT_PATTERN.finditer(html)

    date_match = next(date_iter, None)
    event_match = next(event_iter, None)

    items = []
    seen_slugs = set()

    while date_match is not None or event_match is not None:
        # Decide which comes first in document order
        use_date = (
            date_match is not None and (
                event_match is None or date_match.start() < event_match.start()
            )
        )

        if use_date:
            date_text = date_match.group(1).strip()
            if date_text:  # ignore empty matches
                items.append({'is_date_header': True, 'date': date_text})
            date_match = next(date_iter, None)
        else:
            event_id = event_match.group(1)
            slug = event_match.group(2)
            inner_html = event_match.group(3) or ''
            league_raw = event_match.group(4) or ''

            if slug not in seen_slugs:
                seen_slugs.add(slug)

                is_live = bool(LIVE_IMG_PATTERN.search(inner_html))
                name = TEAM_STRIP_PATTERN.sub('', inner_html).strip()
                name = name.replace('&amp;', '&').replace('&ndash;', ' \u2013 ').replace('&#8211;', ' \u2013 ')
                name = name.strip()

                evdesc_text = TEAM_STRIP_PATTERN.sub('', league_raw).strip()
                # Normalize whitespace (evdesc has lots of \t\n between elements)
                evdesc_clean = re.sub(r'\s+', ' ', evdesc_text).strip()

                # Full "22 February at 14:30" string (for display)
                dt_m = EVDESC_DATETIME.search(evdesc_clean)
                site_datetime = dt_m.group(1).strip() if dt_m else ''

                # Raw hour + minute for timezone offset math
                time_m = EVDESC_TIME.search(evdesc_clean)
                if time_m:
                    site_hour = int(time_m.group(1))
                    site_minute = int(time_m.group(2))
                    time_str = '{:d}:{:02d}'.format(site_hour, site_minute)
                else:
                    site_hour = -1
                    site_minute = 0
                    time_str = ''

                league_m = EVDESC_LEAGUE.search(evdesc_clean)
                league = league_m.group(1).strip() if league_m else evdesc_clean.strip().strip('()')
                league = league.replace('&amp;', '&')

                event_url = '/enx/eventinfo/{}_{}/'.format(event_id, slug)

                if name:
                    items.append({
                        'is_date_header': False,
                        'event_id': event_id,
                        'slug': slug,
                        'name': name,
                        'league': league,
                        'time': time_str,
                        'site_datetime': site_datetime,
                        'site_hour': site_hour,
                        'site_minute': site_minute,
                        'is_live': is_live,
                        'url': event_url,
                    })

            event_match = next(event_iter, None)

    event_count = sum(1 for i in items if not i.get('is_date_header'))
    log('Scraped {} events from {}'.format(event_count, url))
    return items


# ---------------------------------------------------------------------------
# Search results
# Page: /enx/megasearch/?msq={query}
# Same event link structure as event list
# ---------------------------------------------------------------------------
def scrape_search(base_url, query):
    """Search for events/teams matching query. Returns same format as scrape_events."""
    import urllib.parse
    url = base_url + '/enx/megasearch/?msq=' + urllib.parse.quote_plus(query)
    return scrape_events(url)


# ---------------------------------------------------------------------------
# Stream links scraping
# Page: /enx/eventinfo/{event_id}_{slug}/
#
# Real HTML structure (confirmed from live page):
#   div#links_block
#     table.lnktbj   ← one per stream (NOT table.charity)
#       <td><img title="English" ...>          ← language
#       <td class="bitrate">1917kbps</td>      ← bitrate
#       <td><img OnClick="ratelink(2958288, 1, ...)">   ← lid in onclick
#       <td class="rate"><div id="rali2958288">95%</div>  ← quality (lid embedded)
#       <td><a href="//cdn.livetv873.me/webplayer2.php?t=alieztv&c=233080&eid=341350861&lid=2958288...">
#
# We extract all stream entries by finding each link's lid from:
#   OnClick="show_webplayer(..., lid, ...)"  OR  ratelink(lid, ...)
# Then build the CDN URL from those parameters.
# ---------------------------------------------------------------------------

# Primary: extract lid from the ratelink onclick attribute
STREAM_RATELINK_PATTERN = re.compile(r'ratelink\((\d+),\s*1,')

# Extract CDN href — easiest way to get the full player URL
STREAM_CDN_HREF = re.compile(
    r'href="(//cdn\.[^"]+webplayer2?\.php[^"]+)"'
)

# Extract bitrate from class="bitrate" td
STREAM_BITRATE_PATTERN = re.compile(r'class="bitrate"[^>]*>(\d+)kbps')

# Extract language from img title (flag image)
STREAM_LANG_PATTERN_NEW = re.compile(r'<img\s[^>]*title="([^"]+)"[^>]*/?>.*?class="bitrate"', re.DOTALL)

# Extract quality: either from div id="raliLID" content OR from rate div width/color
STREAM_QUALITY_CLASS = re.compile(r'class="rate"[^>]*>.*?(\d+)<span class="pc">%', re.DOTALL)


def scrape_streams(base_url, event_url):
    """
    Scrape stream links from an event detail page.

    Returns a list of dicts:
      {
        'link_id': str,       # e.g. "2958288"
        'bitrate': int,       # kbps, e.g. 1917
        'quality': int,       # % e.g. 95
        'language': str,      # e.g. "English"
        'cdn_url': str,       # full CDN webplayer URL (// protocol-relative)
        'player_url': str,    # https:// version of cdn_url
      }
    """
    full_url = base_url + event_url
    html = _get(full_url, referer=base_url + '/enx/')
    if not html:
        return []

    # Find the links_block section
    lb_start = html.find('id="links_block"')
    if lb_start < 0:
        lb_start = html.find("id='links_block'")
    if lb_start < 0:
        log('links_block div not found in ' + event_url, 'warning')
        return []

    # Take a large chunk from links_block to end of page
    search_area = html[lb_start:lb_start + 50000]

    streams = []
    seen_lids = set()

    # Find each lnktbj table — one per stream row
    for table_m in re.finditer(r'class="lnktbj"(.*?)(?=class="lnktbj"|id="links_block_sop"|id="links_end"|$)',
                                search_area, re.DOTALL):
        chunk = table_m.group(0)

        # Extract link_id from ratelink onclick
        lid_m = STREAM_RATELINK_PATTERN.search(chunk)
        if not lid_m:
            # Fallback: extract from rali div id
            lid_m2 = re.search(r'id="rali(\d+)"', chunk)
            if not lid_m2:
                continue
            link_id = lid_m2.group(1)
        else:
            link_id = lid_m.group(1)

        if link_id in seen_lids:
            continue
        seen_lids.add(link_id)

        # Extract CDN href
        cdn_m = STREAM_CDN_HREF.search(chunk)
        cdn_url = cdn_m.group(1) if cdn_m else ''
        player_url = 'https:' + cdn_url if cdn_url.startswith('//') else cdn_url

        # Extract bitrate
        rate_m = STREAM_BITRATE_PATTERN.search(chunk)
        bitrate = int(rate_m.group(1)) if rate_m else 0

        # Extract quality percentage
        qual_m = STREAM_QUALITY_CLASS.search(chunk)
        quality = int(qual_m.group(1)) if qual_m else 0

        # Extract language from flag img title before the bitrate td
        lang_m = re.search(r'<img[^>]+title="([^"]+)"[^>]*/?>(?!</a>)', chunk)
        language = lang_m.group(1) if lang_m else 'Unknown'

        streams.append({
            'link_id': link_id,
            'bitrate': bitrate,
            'quality': quality,
            'language': language,
            'cdn_url': cdn_url,
            'player_url': player_url,
        })

    # Sort: best quality first, then by bitrate
    streams.sort(key=lambda s: (-s['quality'], -s['bitrate']))

    log('Scraped {} streams for {}'.format(len(streams), event_url))
    return streams


# ---------------------------------------------------------------------------
# Video archive
# Page: /enx/video/
# Each highlight row: thumbnail, title (teams), sport, show video link
# ---------------------------------------------------------------------------
VIDEO_PATTERN = re.compile(
    r'href="/enx/showvideo/(\d+)/"[^>]*>\s*(.*?)\s*</a>',
    re.DOTALL
)
VIDEO_THUMB_PATTERN = re.compile(r'<img[^>]+src="([^"]+)"[^>]*/>')


def scrape_video_archive(url):
    """
    Scrape the video highlights archive.

    Returns list of dicts: {'video_id', 'title', 'thumb', 'url'}
    """
    html = _get(url)
    if not html:
        return []

    videos = []
    seen = set()
    for m in VIDEO_PATTERN.finditer(html):
        video_id = m.group(1)
        if video_id in seen:
            continue
        seen.add(video_id)

        title_raw = m.group(2)
        title = TEAM_STRIP_PATTERN.sub('', title_raw).strip()
        title = title.replace('&amp;', '&').replace('&ndash;', '–').replace('&#8211;', '–')

        # Try to find thumbnail near the link
        start = max(0, m.start() - 300)
        ctx = html[start:m.end()]
        thumb_m = VIDEO_THUMB_PATTERN.search(ctx)
        thumb = thumb_m.group(1) if thumb_m else ''
        if thumb and not thumb.startswith('http'):
            thumb = 'https://livetv.sx' + thumb

        if title:
            videos.append({
                'video_id': video_id,
                'title': title,
                'thumb': thumb,
                'url': '/enx/showvideo/{}/'.format(video_id),
            })

    log('Scraped {} videos from {}'.format(len(videos), url), 'debug')
    return videos
