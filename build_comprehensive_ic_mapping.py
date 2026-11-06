"""
High-speed multithreaded PMFBY Insurance Company comprehensive mapping builder.
Scrapes hierarchy across years (2018-2026), seasons, and schemes.
Saves to data/pmfby/ic_comprehensive_mapping.json.
"""

import urllib.request
import ssl
import json
import base64
import os
import concurrent.futures
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

def fetch_and_decrypt(url):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
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

def clean_ic(raw):
    if not raw:
        return "AIC of India"
    u = str(raw).upper()
    if "AGRICULTURE INSURANCE" in u or "AIC" in u: return "AIC of India"
    if "BAJAJ" in u: return "Bajaj Allianz"
    if "UNIVERSAL SOMPO" in u: return "Universal Sompo"
    if "FUTURE GENERALI" in u: return "Future Generali"
    if "HDFC" in u: return "HDFC ERGO"
    if "ICICI" in u: return "ICICI Lombard"
    if "IFFCO" in u: return "IFFCO TOKIO"
    if "RELIANCE" in u: return "Reliance General"
    if "SBI" in u: return "SBI General"
    if "TATA" in u: return "Tata AIG"
    if "CHOLA" in u: return "Cholamandalam MS"
    if "NATIONAL INSURANCE" in u: return "National Insurance"
    if "NEW INDIA" in u: return "New India Assurance"
    if "ORIENTAL" in u: return "Oriental Insurance"
    if "UNITED INDIA" in u: return "United India Insurance"
    if "KSHEMA" in u: return "Kshema General"
    return str(raw).title()

def fetch_task(item):
    yr = item.get('year')
    sn = item.get('seasonCode', '01')
    sch = item.get('schemeCode', '02')
    sc = str(item.get('stateCode', '')).strip()
    state_id = item.get('stateID')
    sssy_id = item.get('sssyID')
    st_name = item.get('sssyName', {}).get('stateName', '')
    
    if not state_id or not sssy_id:
        return None
        
    u = f'https://www.pmfby.gov.in/landingPage/districtState?stateID={state_id}&sssyID={sssy_id}'
    try:
        res = fetch_and_decrypt(u)
        level3 = res.get('data', {}).get('hierarchy', {}).get('level3', [])
        return {
            "yr": yr, "sn": sn, "sch": sch, "sc": sc, "st_name": st_name,
            "level3": level3
        }
    except Exception as e:
        return None

def main():
    os.makedirs("data/pmfby", exist_ok=True)
    out_file = "data/pmfby/ic_comprehensive_mapping.json"
    
    mapping = {
        "district_map": {},
        "state_map": {},
        "all_companies": set()
    }
    
    # 1. Preload previous mapping if available
    if os.path.exists("data/pmfby/ic_district_mapping.json"):
        try:
            with open("data/pmfby/ic_district_mapping.json", "r", encoding="utf-8") as f:
                old = json.load(f)
                for yr, dists in old.items():
                    for k, v in dists.items():
                        c_name = v.get("company_name", "")
                        c_short = clean_ic(c_name)
                        info = {"name": c_name, "short": c_short}
                        mapping["district_map"][f"{yr}_{k}"] = info
                        mapping["district_map"][k] = info
                        mapping["all_companies"].add(c_short)
        except Exception as e:
            print("Error loading old mapping:", e, flush=True)

    print("Fetching SSSY list...", flush=True)
    sssy_url = 'https://www.pmfby.gov.in/landingPage/sssyList'
    sssy_data = fetch_and_decrypt(sssy_url).get('data', [])
    print(f"Total SSSY entries: {len(sssy_data)}", flush=True)

    # Filter to years 2018-2026, deduplicating by (year, season, scheme, stateCode)
    seen = set()
    tasks = []
    for it in sssy_data:
        yr = it.get('year')
        if yr not in ['2018', '2019', '2020', '2021', '2022', '2023', '2024', '2025', '2026']:
            continue
        sc = str(it.get('stateCode', '')).strip()
        sn = str(it.get('seasonCode', '01')).strip()
        sch = str(it.get('schemeCode', '02')).strip()
        k = f"{yr}_{sn}_{sch}_{sc}"
        if k in seen:
            continue
        seen.add(k)
        tasks.append(it)

    print(f"Executing {len(tasks)} tasks with ThreadPoolExecutor (10 workers)...", flush=True)
    
    completed_count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_task = {executor.submit(fetch_task, t): t for t in tasks}
        for future in concurrent.futures.as_completed(future_to_task):
            res = future.result()
            completed_count += 1
            if completed_count % 50 == 0:
                print(f"  Progress: {completed_count}/{len(tasks)} requests completed...", flush=True)
            if not res or not res["level3"]:
                continue
            
            yr, sn, sch, sc = res["yr"], res["sn"], res["sch"], res["sc"]
            st_cos = set()
            for dist in res["level3"]:
                d_code = str(dist.get('level3Code', '')).strip()
                d_name = str(dist.get('level3Name', '')).strip().upper()
                d_name_norm = d_name.replace(" ", "")
                ic = dist.get('insuranceCompany', {})
                ic_name = ic.get('insuranceCompanyName', '').strip()
                if not ic_name:
                    continue
                ic_short = clean_ic(ic_name)
                st_cos.add(ic_short)
                mapping["all_companies"].add(ic_short)
                
                info = {"name": ic_name, "short": ic_short}
                mapping["district_map"][f"{yr}_{sn}_{sch}_{sc}_{d_code}"] = info
                mapping["district_map"][f"{yr}_{sn}_{sch}_{sc}_{d_name}"] = info
                mapping["district_map"][f"{yr}_{sn}_{sch}_{sc}_{d_name_norm}"] = info
                mapping["district_map"][f"{yr}_{sc}_{d_code}"] = info
                mapping["district_map"][f"{yr}_{sc}_{d_name}"] = info
                mapping["district_map"][f"{sc}_{d_code}"] = info
                mapping["district_map"][f"{sc}_{d_name}"] = info

            if st_cos:
                mapping["state_map"][f"{yr}_{sn}_{sch}_{sc}"] = sorted(list(st_cos))
                mapping["state_map"][f"{yr}_{sc}"] = sorted(list(st_cos))
                mapping["state_map"][f"{sc}"] = sorted(list(st_cos))

    mapping["all_companies"] = sorted(list(mapping["all_companies"]))
    print(f"\nFinished! Total mapped entries: {len(mapping['district_map'])}, Unique companies: {len(mapping['all_companies'])}", flush=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2)
    print(f"Saved comprehensive mapping to {out_file}", flush=True)

if __name__ == '__main__':
    main()
