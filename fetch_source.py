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
    'Referer': 'https://cdn.livetv873.me/'
})

try:
    r = s.get('https://viewembed.ru/channel/Sportklub2%5BSerbia%5D', verify=False, timeout=15)
    with open('sportklub_viewembed.html', 'wb') as f:
        f.write(r.content)
    print("Success")
except Exception as e:
    print(f"Error: {e}")
