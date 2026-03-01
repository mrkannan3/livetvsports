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

# Volleyball (Sportklub2)
sk2_url = "https://viewembed.ru/channel/Sportklub2%5BSerbia%5D"
# Tennis (T9)
t9_url = "https://stellarthread.com/wiki.php?player=desktop&live=t9"

try:
    print(f"Fetching {sk2_url}...")
    r1 = s.get(sk2_url, headers={'Referer': 'https://cdn.livetv873.me/'}, verify=False, timeout=15)
    with open('debug_sk2.html', 'wb') as f: f.write(r1.content)
    
    print(f"Fetching {t9_url}...")
    r2 = s.get(t9_url, headers={'Referer': 'https://wikisport.club/'}, verify=False, timeout=15)
    with open('debug_t9.html', 'wb') as f: f.write(r2.content)
    print("Done")
except Exception as e:
    print(f"Error: {e}")
