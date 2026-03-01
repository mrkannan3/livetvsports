import requests
import urllib3
import sys
import ssl
from requests.adapters import HTTPAdapter

urllib3.disable_warnings()

class SSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = context
        return super(SSLAdapter, self).init_poolmanager(*args, **kwargs)

s = requests.Session()
s.mount('https://', SSLAdapter())
s.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
})

# The resolved URL from user logs
m3u8_url = "https://wikisport.club/hls/stream.m3u8?ch=spn"
referer = "https://wikisport.club/court/t9.php"

print(f"Testing stream: {m3u8_url}")
headers = {'Referer': referer}

try:
    r = s.get(m3u8_url, headers=headers, verify=False, timeout=10)
    print(f"Status: {r.status_code}")
    print(f"Content-Type: {r.headers.get('Content-Type')}")
    print(f"Content (first 100 bytes): {r.content[:100]}")
except Exception as e:
    print(f"Error: {e}")
