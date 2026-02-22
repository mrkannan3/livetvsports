# main.py — Entry point and URL router for plugin.video.livetvsxsports
#
# Mode map:
#   0  = Sport category menu (home)
#   1  = Event list for a sport (allupcomingsports/{sport_id}/)
#   2  = All upcoming events (any sport)
#   3  = Search events
#   4  = Show streams for an event
#   5  = Play a stream (resolve + setResolvedUrl)
#   6  = Video archive menu
#   7  = List highlight videos
#   8  = Play a highlight video
#   9  = Open addon settings
#  10  = Live scores (informational listing)

import sys
import urllib.parse
import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

ADDON = xbmcaddon.Addon(id='plugin.video.livetvsports')
HANDLE = int(sys.argv[1])
BASE_PLUGIN_URL = sys.argv[0]

# Import our modules — use full path to avoid relative import issues in Kodi
sys.path.insert(0, xbmcaddon.Addon(id='plugin.video.livetvsports').getAddonInfo('path'))
from resources.lib.utils import log, SPORTS, get_sport_icon_url, get_base_url, get_setting
from resources.lib import scraper, resolver


# ---------------------------------------------------------------------------
# URL building / parsing helpers
# ---------------------------------------------------------------------------
def build_url(mode, **kwargs):
    """Build a plugin:// URL with query parameters."""
    params = {'mode': str(mode)}
    params.update({k: str(v) for k, v in kwargs.items()})
    return BASE_PLUGIN_URL + '?' + urllib.parse.urlencode(params)


def get_params():
    """Parse query string from sys.argv[2]."""
    param_str = sys.argv[2]
    if param_str.startswith('?'):
        param_str = param_str[1:]
    if not param_str:
        return {}
    return dict(urllib.parse.parse_qsl(param_str))


# ---------------------------------------------------------------------------
# Directory item helpers
# ---------------------------------------------------------------------------
def add_dir(label, url, is_folder=True, thumb='', fanart='',
            info=None, properties=None, context_menu=None):
    """Add a directory or playable item to Kodi's listing."""
    li = xbmcgui.ListItem(label)
    art = {'icon': thumb or 'DefaultFolder.png',
           'thumb': thumb or 'DefaultFolder.png',
           'fanart': fanart or ADDON.getAddonInfo('fanart')}
    li.setArt(art)
    if info:
        li.setInfo(type='Video', infoLabels=info)
    if properties:
        for k, v in properties.items():
            li.setProperty(k, v)
    if context_menu:
        li.addContextMenuItems(context_menu)
    if not is_folder:
        li.setProperty('IsPlayable', 'true')
    xbmcplugin.addDirectoryItem(handle=HANDLE, url=url, listitem=li, isFolder=is_folder)


def end_dir(cache=True, content='videos', sort_methods=None):
    """Finalise the directory listing."""
    xbmcplugin.setContent(HANDLE, content)
    if sort_methods:
        for m in sort_methods:
            xbmcplugin.addSortMethod(HANDLE, m)
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=cache)


# ---------------------------------------------------------------------------
# Mode 0 — Sport category home menu
# ---------------------------------------------------------------------------
def show_sports_menu():
    """Display the list of sports as the home menu."""
    base_url = get_base_url()

    # Detect and save the current CDN domain (runs in background-ish, quick)
    try:
        cdn = scraper.get_cdn_domain(base_url)
        ADDON.setSetting('cdn_domain', cdn)
        log('CDN domain refreshed: ' + cdn)
    except Exception as e:
        log('CDN detection failed: ' + str(e), 'warning')

    # Entry: All upcoming events (every sport)
    add_dir(
        label='📺  All Upcoming Broadcasts',
        url=build_url(2),
        thumb='https://cdn.livetv873.me/img/oglogo.png',
    )
    # Entry: Search
    add_dir(
        label='🔍  Search',
        url=build_url(3),
        thumb='https://cdn.livetv.sx/img/sport/18.gif', # Using Athletics for search feel
    )
    # Entry: Video Archive / Highlights
    add_dir(
        label='🎬  Video Archive & Highlights',
        url=build_url(6),
        thumb='https://cdn.livetv.sx/img/sport/6.gif',  # Using Boxing/Combat icon for content feel
    )

    # Sport categories
    for sport_id, sport_name in SPORTS:
        icon_url = get_sport_icon_url(sport_id)
        add_dir(
            label=sport_name,
            url=build_url(1, sport_id=sport_id, sport_name=sport_name),
            thumb=icon_url,
        )

    # Settings
    add_dir(
        label='⚙️  Settings',
        url=build_url(9),
        thumb='DefaultAddonService.png',
    )

    end_dir(content='files')


# ---------------------------------------------------------------------------
# Mode 1 — Event list for a specific sport
# ---------------------------------------------------------------------------
def show_sport_events(params):
    sport_id = params.get('sport_id', '1')
    sport_name = urllib.parse.unquote_plus(params.get('sport_name', 'Sport'))
    base_url = get_base_url()

    url = base_url + '/enx/allupcomingsports/{}/'.format(sport_id)
    log('Showing events for sport {} ({})'.format(sport_name, sport_id))

    events = scraper.scrape_events(url)
    _render_events(events, base_url)


# ---------------------------------------------------------------------------
# Mode 2 — All upcoming events (every sport)
# ---------------------------------------------------------------------------
def show_all_events(params):
    base_url = get_base_url()
    url = base_url + '/enx/allupcoming/'
    log('Showing all upcoming events')

    events = scraper.scrape_events(url)
    _render_events(events, base_url)


def _render_events(events, base_url):
    """Render a list of events (and optional date-header separators) as directory items."""
    if not events:
        xbmcgui.Dialog().notification(
            'LiveTV Sports', 'No events found. Try again later.',
            xbmcgui.NOTIFICATION_INFO, 3000
        )
        end_dir(content='files')
        return

    live_first = get_setting('live_first') == 'true'

    # Timezone offset (hours) to convert site time → local time
    try:
        tz_offset = int(get_setting('tz_offset') or '-7')
    except (ValueError, TypeError):
        tz_offset = -7

    # Check if the list contains date-header separators (already ordered by date)
    has_date_headers = any(item.get('is_date_header') for item in events)

    # Only apply live-first sort when there are no date headers; otherwise keep
    # the server's chronological grouping intact.
    if live_first and not has_date_headers:
        events = sorted(events, key=lambda e: (0 if e.get('is_live') else 1))

    for item in events:
        if item.get('is_date_header'):
            # Render a non-playable section header for the date group
            date_label = '[B][COLOR gold]\u2500\u2500  {}  \u2500\u2500[/COLOR][/B]'.format(item['date'])
            li = xbmcgui.ListItem(date_label)
            li.setProperty('IsPlayable', 'false')
            xbmcplugin.addDirectoryItem(HANDLE, '', li, False)
            continue

        # Apply timezone offset to site time and format as 12-hour AM/PM
        site_hour = item.get('site_hour', -1)
        site_minute = item.get('site_minute', 0)
        if site_hour >= 0:
            if tz_offset != 0:
                total_minutes = site_hour * 60 + site_minute + tz_offset * 60
                total_minutes = total_minutes % (24 * 60)
                local_hour = total_minutes // 60
                local_minute = total_minutes % 60
            else:
                local_hour = site_hour
                local_minute = site_minute
            period = 'AM' if local_hour < 12 else 'PM'
            hour_12 = local_hour % 12 or 12  # 0 → 12, 13 → 1, etc.
            local_time = '{}:{:02d} {}'.format(hour_12, local_minute, period)
        else:
            local_time = ''

        # Build plain label: [LIVE tag] + "EventName (7:30 AM - T20 World Cup)"
        live_tag = '[COLOR red][LIVE][/COLOR] ' if item.get('is_live') else ''
        league = item.get('league', '')

        extra = ' - '.join(p for p in [local_time, league] if p)
        name_str = item['name']
        if extra:
            name_str = '{} ({})'.format(name_str, extra)

        label = name_str

        log('EVENT LABEL: ' + repr(label))   # DEBUG — visible in kodi.log

        li = xbmcgui.ListItem(label)
        li.setInfo('video', {'Title': name_str,
                             'Plot': '{} - {}'.format(league, local_time)})
        li.setArt({'thumb': 'DefaultVideo.png'})

        url = build_url(4,
                        event_id=item['event_id'],
                        slug=item['slug'],
                        event_name=urllib.parse.quote_plus(item['name']))
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)

    end_dir(content='files', sort_methods=[xbmcplugin.SORT_METHOD_NONE])


# ---------------------------------------------------------------------------
# Mode 3 — Search
# ---------------------------------------------------------------------------
def search_events(params):
    kb = xbmc.Keyboard('', 'Search for team or event')
    kb.doModal()
    if not kb.isConfirmed():
        end_dir(content='files')
        return

    query = kb.getText().strip()
    if not query:
        end_dir(content='files')
        return

    base_url = get_base_url()
    log('Searching for: ' + query)
    events = scraper.scrape_search(base_url, query)
    _render_events(events, base_url)


# ---------------------------------------------------------------------------
# Mode 4 — Show streams for an event
# ---------------------------------------------------------------------------
def show_streams(params):
    event_id = params.get('event_id', '')
    slug = params.get('slug', '')
    event_name = urllib.parse.unquote_plus(params.get('event_name', ''))
    base_url = get_base_url()

    event_url = '/enx/eventinfo/{}_{}/'.format(event_id, slug)
    log('Fetching streams for event: ' + event_url)

    streams = scraper.scrape_streams(base_url, event_url)

    if not streams:
        xbmcgui.Dialog().notification(
            'LiveTV Sports',
            'No streams found for this event yet. Try again closer to kick-off.',
            xbmcgui.NOTIFICATION_WARNING, 4000
        )
        end_dir(content='files')
        return

    for i, stream in enumerate(streams):
        quality_color = 'green' if stream['quality'] >= 80 else ('orange' if stream['quality'] >= 50 else 'red')
        label = (
            '[COLOR {color}]{quality}%[/COLOR]  '
            '{bitrate}kbps  [{lang}]  Stream {num}'
        ).format(
            color=quality_color,
            quality=stream['quality'],
            bitrate=stream['bitrate'],
            lang=stream['language'],
            num=i + 1,
        )

        play_url = build_url(5,
                             player_url=urllib.parse.quote_plus(stream['player_url']),
                             link_id=stream['link_id'],
                             event_id=event_id,
                             event_name=urllib.parse.quote_plus(event_name))
        add_dir(
            label=label,
            url=play_url,
            is_folder=False,
            thumb='DefaultVideo.png',
            info={'Title': event_name,
                  'Plot': '{} — {}kbps — {}%'.format(stream['language'], stream['bitrate'], stream['quality'])},
            properties={'IsPlayable': 'true'},
        )

    end_dir(content='videos', sort_methods=[xbmcplugin.SORT_METHOD_NONE])


# ---------------------------------------------------------------------------
# Mode 5 — Play a stream
# ---------------------------------------------------------------------------
def play_stream(params):
    link_id = params.get('link_id', '')
    event_id = params.get('event_id', '')
    event_name = urllib.parse.unquote_plus(params.get('event_name', 'Live Stream'))
    player_url = urllib.parse.unquote_plus(params.get('player_url', ''))

    log('Playing stream: link_id={} event_id={}'.format(link_id, event_id))
    log('CDN player URL: ' + player_url)

    # Resolve: fetch the CDN webplayer page → follow iframe → extract m3u8
    stream_url = resolver.resolve_stream(player_url, event_id)

    if not stream_url:
        xbmcgui.Dialog().ok(
            'LiveTV Sports — Stream Error',
            'Could not resolve this stream. Please try a different stream.'
        )
        return

    log('Resolved stream URL: ' + stream_url)

    li = xbmcgui.ListItem(event_name)
    li.setInfo('video', {'Title': event_name})
    li.setProperty('IsPlayable', 'true')
    li.setPath(stream_url)
    xbmcplugin.setResolvedUrl(HANDLE, True, li)




# ---------------------------------------------------------------------------
# Mode 6 — Video archive menu
# ---------------------------------------------------------------------------
def show_video_archive_menu(params):
    base_url = get_base_url()

    # Main archive page (today's date)
    add_dir(
        label="📅  Today's Highlights",
        url=build_url(7, archive_url=urllib.parse.quote_plus(base_url + '/enx/video/')),
        thumb='DefaultRecentlyAddedMovies.png',
    )

    # Show a few recent dates
    import datetime
    today = datetime.date.today()
    for i in range(1, 8):
        d = today - datetime.timedelta(days=i)
        date_str = d.strftime('%Y-%m-%d')
        label_str = d.strftime('%A, %d %B %Y')
        archive_url = base_url + '/enx/video/?date=' + date_str
        add_dir(
            label='📅  ' + label_str,
            url=build_url(7, archive_url=urllib.parse.quote_plus(archive_url)),
            thumb='DefaultYear.png',
        )

    end_dir(content='files')


# ---------------------------------------------------------------------------
# Mode 7 — List highlight videos
# ---------------------------------------------------------------------------
def list_videos(params):
    archive_url = urllib.parse.unquote_plus(params.get('archive_url', ''))
    base_url = get_base_url()
    if not archive_url:
        archive_url = base_url + '/enx/video/'

    log('Listing videos from: ' + archive_url)
    videos = scraper.scrape_video_archive(archive_url)

    if not videos:
        xbmcgui.Dialog().notification(
            'LiveTV Sports', 'No highlights found for this date.',
            xbmcgui.NOTIFICATION_INFO, 3000
        )
        end_dir(content='videos')
        return

    for video in videos:
        add_dir(
            label=video['title'],
            url=build_url(8,
                          video_url=urllib.parse.quote_plus(video['url']),
                          title=urllib.parse.quote_plus(video['title'])),
            is_folder=False,
            thumb=video['thumb'],
            info={'Title': video['title']},
            properties={'IsPlayable': 'true'},
        )

    end_dir(content='videos', sort_methods=[xbmcplugin.SORT_METHOD_NONE])


# ---------------------------------------------------------------------------
# Mode 8 — Play a highlight video
# ---------------------------------------------------------------------------
def play_video(params):
    video_url = urllib.parse.unquote_plus(params.get('video_url', ''))
    title = urllib.parse.unquote_plus(params.get('title', 'Highlight'))
    base_url = get_base_url()

    log('Playing highlight: ' + video_url)
    stream_url = resolver.resolve_highlight(base_url, video_url)

    if not stream_url:
        xbmcgui.Dialog().ok(
            'LiveTV Sports — Video Error',
            'Could not find a playable video for this highlight.'
        )
        return

    log('Resolved highlight URL: ' + stream_url)

    li = xbmcgui.ListItem(title)
    li.setInfo('video', {'Title': title})
    li.setProperty('IsPlayable', 'true')
    li.setPath(stream_url)
    xbmcplugin.setResolvedUrl(HANDLE, True, li)


# ---------------------------------------------------------------------------
# Mode 9 — Open settings
# ---------------------------------------------------------------------------
def open_settings(params):
    ADDON.openSettings()


# ---------------------------------------------------------------------------
# Mode 10 — Live scores (informational — scrape /enx/livescore/)
# ---------------------------------------------------------------------------
def show_live_scores(params):
    base_url = get_base_url()
    url = base_url + '/enx/livescore/'
    events = scraper.scrape_events(url)
    _render_events(events, base_url)


# ---------------------------------------------------------------------------
# Main router
# ---------------------------------------------------------------------------
MODE_MAP = {
    0:  show_sports_menu,
    1:  show_sport_events,
    2:  show_all_events,
    3:  search_events,
    4:  show_streams,
    5:  play_stream,
    6:  show_video_archive_menu,
    7:  list_videos,
    8:  play_video,
    9:  open_settings,
    10: show_live_scores,
}

if __name__ == '__main__':
    params = get_params()
    mode = int(params.get('mode', 0))
    log('Mode: {}  Params: {}'.format(mode, params), 'debug')

    handler = MODE_MAP.get(mode)
    if handler:
        if mode == 0:
            handler()
        else:
            handler(params)
    else:
        log('Unknown mode: {}'.format(mode), 'error')
        show_sports_menu()
