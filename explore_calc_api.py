import urllib.request, ssl, re

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request('https://www.pmfby.gov.in/', headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
    html = resp.read().decode('utf-8', errors='ignore')

scripts = re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', html)
print('Scripts found on home page:', len(scripts))
for s in scripts:
    print(' ', s)

# Also check for API endpoints mentioned in JS
for s in scripts:
    if 'app' in s or 'main' in s or 'chunk' in s:
        full_url = s if s.startswith('http') else f'https://www.pmfby.gov.in{s}'
        try:
            req_js = urllib.request.Request(full_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req_js, context=ctx, timeout=10) as rjs:
                js_content = rjs.read().decode('utf-8', errors='ignore')
            print(f'Fetched {s} (length: {len(js_content)})')
            # Search for landingPage or goiConfig
            endpoints = set(re.findall(r'["\'](?:landingPage|goiConfig)/([a-zA-Z0-9_]+)["\']', js_content))
            print(f'  Endpoints in {s}:', sorted(list(endpoints)))
        except Exception as e:
            print(f'  Error fetching {s}: {e}')
