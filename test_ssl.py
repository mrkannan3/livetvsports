import requests
import urllib3
import sys

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

url = "https://viewembed.ru/channel/SkySportsCricket%5BUK%5D"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
}

print(f"Testing URL: {url}")
try:
    r = requests.get(url, headers=headers, timeout=15, verify=False)
    print(f"Status: {r.status_code}")
    print(f"Length: {len(r.text)}")
except Exception as e:
    print(f"Error: {e}")
