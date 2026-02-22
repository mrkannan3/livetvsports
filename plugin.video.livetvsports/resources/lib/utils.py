# utils.py — Logging, constants, and helper utilities for plugin.video.livetvsxsports

import xbmc
import xbmcaddon

ADDON = xbmcaddon.Addon(id='plugin.video.livetvsports')
ADDON_ID = 'plugin.video.livetvsports'
ADDON_NAME = 'LiveTV Sports'

BASE_URL = ADDON.getSetting('base_url').rstrip('/')
CDN_DOMAIN = ADDON.getSetting('cdn_domain') or 'livetv873.me'
DEBUG = ADDON.getSetting('debug_logging') == 'true'

USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/131.0.0.0 Safari/537.36'
)

# Sport categories with confirmed IDs from sidebar
SPORTS = [
    (1,  'Football'),
    (2,  'Ice Hockey'),
    (3,  'Basketball'),
    (4,  'Tennis'),
    (5,  'Volleyball'),
    (6,  'Boxing'),
    (7,  'Racing'),
    (8,  'Handball'),
    (11, 'Rugby League'),
    (12, 'Futsal'),
    (16, 'Bandy'),
    (17, 'Baseball'),
    (18, 'Athletics'),
    (19, 'Curling'),
    (20, 'Water Polo'),
    (21, 'Cycling'),
    (41, 'Cricket'),
    (54, 'Winter Sport'),
]


def get_sport_icon_url(sport_id):
    """Build the official GIF icon URL using the current CDN domain."""
    return 'https://cdn.{}/img/sport/{}.gif'.format(CDN_DOMAIN, sport_id)


def log(message, level='info'):
    """Log a message to the Kodi log."""
    prefix = '[{}] '.format(ADDON_NAME)
    if level == 'error':
        xbmc.log(prefix + str(message), level=xbmc.LOGERROR)
    elif level == 'warning':
        xbmc.log(prefix + str(message), level=xbmc.LOGWARNING)
    elif DEBUG or level == 'debug':
        xbmc.log(prefix + str(message), level=xbmc.LOGDEBUG)
    else:
        xbmc.log(prefix + str(message), level=xbmc.LOGINFO)


def get_setting(key):
    """Reload a setting fresh (avoids stale cache on ADDON singleton)."""
    return xbmcaddon.Addon(id=ADDON_ID).getSetting(key)


def get_base_url():
    return get_setting('base_url').rstrip('/')
