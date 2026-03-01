import requests
import urllib3
import sys
import ssl
import time
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
    'Referer': 'https://viewembed.ru/channel/Sportklub2%5BSerbia%5D'
})

cid = "primasportklub2"
token = "primasportklub2||1772332761|1772419161|7102b7629bd220552f4cb7e2b0c461ac871c48b5d1f8bf5a7e6717bc9b4726ed"
t = 1772332761 # From page

api = f'https://viewembed.ru/get_stream?id={cid}&token={token.replace("|", "%7C")}&t={t}'
print(f"Testing API: {api}")

try:
    r = s.get(api, verify=False, timeout=15)
    print(f"Status: {r.status_code}")
    sys.stdout.buffer.write(r.content)
except Exception as e:
    print(f"Error: {e}")
