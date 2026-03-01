import requests
import urllib3
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
    'Referer': 'https://ksohls.ru/'
})

url = "https://chevy.adsfadfds.cfd/proxy/max2/primamovistar2/mono.css"
print(f"Fetching {url}...")
try:
    r = s.get(url, verify=False, timeout=10)
    print(f"Status: {r.status_code}")
    print(f"Content-Type: {r.headers.get('Content-Type')}")
    print(f"Body (first 200 bytes): {r.text[:200]}")
except Exception as e:
    print(f"Error: {e}")
