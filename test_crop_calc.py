import urllib.request, ssl, json, base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

def fetch_and_decrypt(url):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
        text = resp.read().decode('utf-8')
    parts = text.split('.')
    key_str = base64.b64decode(parts[2]).decode('utf-8')
    iv_str = base64.b64decode(parts[3]).decode('utf-8')
    cipher = Cipher(algorithms.AES(key_str.encode('utf-8')), modes.CBC(iv_str.encode('utf-8')), backend=default_backend())
    decrypted = cipher.decryptor().update(bytes.fromhex(parts[1])) + cipher.decryptor().finalize()
    idx = decrypted.rfind(b'}')
    if idx != -1:
        return json.loads(decrypted[:idx+1].decode('utf-8'))
    pad = decrypted[-1]
    if isinstance(pad, int) and pad <= 16:
        decrypted = decrypted[:-pad]
    return json.loads(decrypted.decode('utf-8'))

# Let's test cropList for a known sssy and district:
# In our previous explore:
# 2024 Kharif PMFBY Karnataka (sssyID '02012924', Bagalkot districtID or districtCode)
# Let's inspect districtState for 2024 Kharif Karnataka:
u_dist = 'https://www.pmfby.gov.in/landingPage/districtState?stateID=1A20649E-499D-4452-8292-1225502C86F0&sssyID=02012924'
# Wait, let's find the stateID and sssyID for Karnataka 2024
sssy_list = fetch_and_decrypt('https://www.pmfby.gov.in/landingPage/sssyList').get('data', [])
karnataka_2024 = next((s for s in sssy_list if s.get('year') == '2024' and s.get('stateCode') == '29' and s.get('seasonCode') == '01' and s.get('schemeCode') == '04'), None)

if karnataka_2024:
    print('Found Karnataka 2024:', karnataka_2024.get('sssyID'), karnataka_2024.get('stateID'))
    u = f"https://www.pmfby.gov.in/landingPage/districtState?stateID={karnataka_2024['stateID']}&sssyID={karnataka_2024['sssyID']}"
    dists = fetch_and_decrypt(u).get('data', {}).get('hierarchy', {}).get('level3', [])
    print(f'Found {len(dists)} districts')
    if dists:
        d = dists[0]
        print('Sample district:', d.get('level3Name'), 'level3ID:', d.get('level3ID'), 'level3Code:', d.get('level3Code'))
        dist_id = d.get('level3ID') or d.get('level3Code')
        
        # Test cropList
        u_crop = f"https://www.pmfby.gov.in/cropNotification/cropList?sssyID={karnataka_2024['sssyID']}&districtID={dist_id}"
        print('Testing cropList URL:', u_crop)
        crop_res = fetch_and_decrypt(u_crop)
        print('Crop list keys:', crop_res.keys())
        crops = crop_res.get('data', [])
        print(f"Found {len(crops)} crops for {d.get('level3Name')}")
        if crops:
            print('Sample crop:', crops[0])
            crop_id = crops[0].get('cropID')
            
            # Test calculatePremium
            u_calc = f"https://www.pmfby.gov.in/landingPage/calculatePremium?sssyID={karnataka_2024['sssyID']}&districtID={dist_id}&cropID={crop_id}"
            print('Testing calculatePremium URL:', u_calc)
            calc_res = fetch_and_decrypt(u_calc)
            print('calculatePremium result:', calc_res)
