import urllib.request, ssl, re

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

files = ['/9bdf039ac729ff81404e.js', '/6c47639d80eeeb82a4ed.js']
for s in files:
    full_url = f'https://www.pmfby.gov.in{s}'
    try:
        req = urllib.request.Request(full_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
            content = resp.read().decode('utf-8', errors='ignore')
        print(f'Fetched {s} (length: {len(content)})')
        matches = set(re.findall(r'landingPage/[a-zA-Z0-9_\?=&]+', content))
        print('LandingPage matches:', sorted(list(matches)))
        matches2 = set(re.findall(r'goiConfig/[a-zA-Z0-9_\?=&]+', content))
        print('goiConfig matches:', sorted(list(matches2)))
        
        # Check any mentions of crop in context
        crop_matches = set(re.findall(r'/[a-zA-Z0-9_]*[Cc]rop[a-zA-Z0-9_]*', content))
        print('Crop matches:', sorted(list(crop_matches)))
        
        # Check premium calculation logic
        prem_matches = set(re.findall(r'[a-zA-Z0-9_]*[Pp]remium[a-zA-Z0-9_]*', content))
        print('Sample premium terms:', list(prem_matches)[:15])
    except Exception as e:
        print(f'Error on {s}: {e}')
