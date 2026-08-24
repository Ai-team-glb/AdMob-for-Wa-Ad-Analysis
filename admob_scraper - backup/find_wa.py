import urllib.request
import re

url = 'https://mahadevelectronic.blogspot.com/2026/08/mahadev-electronics-premium-appliances.html?gad_source=5&gad_campaignid=24105002864&gclid=CjwKCAjwvsvTBhBaEiwAmf-3nne-uLHMD1oYrhPNHq9m-ffC8e4Zdb5ufyqTTJOBdKEM88_OI4zxrRoCqFUQAvD_BwE'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=10) as resp:
    html = resp.read().decode('utf-8', errors='ignore')

print('=== Raw Regex Matches ===')
matches = re.findall(r'https?://[^\s"\'<>]+', html)
for m in set(matches):
    if 'wa.me' in m or 'whatsapp' in m:
        print('WA Link found:', m)

print('=== HTML snippet with whatsapp ===')
for line in html.splitlines():
    if 'whatsapp' in line.lower() or 'wa.me' in line.lower() or 'chat' in line.lower():
        print('Line:', line[:150])

print('=== Text Search in HTML ===')
matches = re.findall(r'https?://[^\s"\'<>]+(?:whatsapp|wa\.me)[^\s"\'<>]*', html, re.IGNORECASE)
for m in set(matches):
    print('RAW MATCH:', m)

for i, line in enumerate(html.splitlines()):
    if 'whatsapp' in line.lower() or 'wa.me' in line.lower():
        print(f"--- Line {i} ---")
        for j in range(max(0, i-2), min(len(html.splitlines()), i+8)):
            print(f"{j}: {html.splitlines()[j]}")
