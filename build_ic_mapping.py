import urllib.request
import ssl
import json
import base64
import os
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

def fetch_and_decrypt(url):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
        text = resp.read().decode('utf-8')
    parts = text.split('.')
    key_str = base64.b64decode(parts[2]).decode('utf-8')
    iv_str = base64.b64decode(parts[3]).decode('utf-8')
    cipher = Cipher(algorithms.AES(key_str.encode('utf-8')), modes.CBC(iv_str.encode('utf-8')), backend=default_backend())
    decryptor = cipher.decryptor()
    ciphertext = bytes.fromhex(parts[1])
    decrypted = decryptor.update(ciphertext) + decryptor.finalize()
    pad = decrypted[-1]
    if isinstance(pad, int) and pad < 16:
        decrypted = decrypted[:-pad]
    return json.loads(decrypted.decode('utf-8'))

os.makedirs("data/pmfby", exist_ok=True)

# Fetch SSSY list
print("Fetching SSSY list...")
sssy_url = 'https://www.pmfby.gov.in/landingPage/sssyList'
sssy_data = fetch_and_decrypt(sssy_url).get('data', [])
print(f"Total SSSY entries: {len(sssy_data)}")

# Map of (year, stateCode, districtCode/Name) -> insuranceCompanyName
mapping = {}

years = ['2024', '2023', '2022']
for yr in years:
    mapping[yr] = {}
    season_items = [it for it in sssy_data if it.get('year') == yr and it.get('seasonCode') == '01' and it.get('schemeCode') in ['02', '04']]
    print(f"\nProcessing Year {yr}: {len(season_items)} state seasons...")
    
    seen_states = set()
    for it in season_items:
        sc = it.get('stateCode')
        if sc in seen_states:
            continue
        seen_states.add(sc)
        
        st_name = it.get('sssyName', {}).get('stateName', '')
        state_id = it.get('stateID')
        sssy_id = it.get('sssyID')
        
        u = f'https://www.pmfby.gov.in/landingPage/districtState?stateID={state_id}&sssyID={sssy_id}'
        try:
            res = fetch_and_decrypt(u)
            hierarchy = res.get('data', {}).get('hierarchy', {})
            # Look for level3 (district level)
            level3 = hierarchy.get('level3', [])
            print(f"  {st_name} ({sc}): {len(level3)} districts")
            
            for dist in level3:
                d_code = str(dist.get('level3Code', '')).strip()
                d_name = str(dist.get('level3Name', '')).strip().upper()
                ic = dist.get('insuranceCompany', {})
                ic_name = ic.get('insuranceCompanyName', 'AGRICULTURE INSURANCE COMPANY').strip()
                ic_code = ic.get('insuranceCompanyCode', '')
                
                # Save by code and upper name
                mapping[yr][f"{sc}_{d_code}"] = {
                    "company_name": ic_name,
                    "company_code": ic_code
                }
                mapping[yr][f"{sc}_{d_name}"] = {
                    "company_name": ic_name,
                    "company_code": ic_code
                }
        except Exception as e:
            print(f"  {st_name} ({sc}) fetch failed: {e}")

out_file = "data/pmfby/ic_district_mapping.json"
with open(out_file, "w", encoding="utf-8") as f:
    json.dump(mapping, f, indent=2)

print(f"\nMapping successfully saved to {out_file}!")
