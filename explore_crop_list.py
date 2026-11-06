import urllib.request, ssl, re

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request('https://www.pmfby.gov.in/6c47639d80eeeb82a4ed.js', headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
    content = resp.read().decode('utf-8', errors='ignore')

idx = 0
while True:
    pos = content.find('fetchCropList', idx)
    if pos == -1: break
    start = max(0, pos - 200)
    end = min(len(content), pos + 500)
    print(f"\n--- fetchCropList at {pos} ---")
    print(content[start:end])
    idx = pos + len('fetchCropList')
