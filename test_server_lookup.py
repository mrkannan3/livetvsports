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
    'Referer': 'https://viewembed.ru/'
})

cid = "primasportklub2"
api = f'https://chevy.vovlacosa.sbs/server_lookup?channel_id={cid}'
print(f"Testing API: {api}")

try:
    r = s.get(api, verify=False, timeout=15)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text}")
except Exception as e:
    print(f"Error: {e}")
