import urllib.request, ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request('https://www.pmfby.gov.in/6c47639d80eeeb82a4ed.js', headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
    content = resp.read().decode('utf-8', errors='ignore')

chunk = content[429000:431500]
with open('crop_fn_snippet2.txt', 'w', encoding='utf-8') as f:
    f.write(chunk)
print('Saved snippet2!')
