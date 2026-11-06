from test_crop_calc import fetch_and_decrypt
import json

# Check crops across several states in 2024 and 2023
sssy_list = fetch_and_decrypt('https://www.pmfby.gov.in/landingPage/sssyList').get('data', [])

# Let's test a few state-districts
test_states = ['28', '22', '18', '29', '27', '35'] # AP, Chhattisgarh, Assam, Karnataka, Maharashtra, A&N

all_crop_data = []

for s in sssy_list:
    if s.get('stateCode') in test_states and s.get('year') in ['2024', '2023']:
        st_name = s.get('sssyName', {}).get('stateName')
        sssy_id = s.get('sssyID')
        st_id = s.get('stateID')
        u = f"https://www.pmfby.gov.in/landingPage/districtState?stateID={st_id}&sssyID={sssy_id}"
        try:
            dists = fetch_and_decrypt(u).get('data', {}).get('hierarchy', {}).get('level3', [])
            if not dists: continue
            print(f"State: {st_name} ({s.get('year')} {s.get('sssyName', {}).get('schemeNameShort')} {s.get('sssyName', {}).get('seasonName')}) has {len(dists)} dists")
            for d in dists[:2]:
                d_id = d.get('level3ID')
                d_name = d.get('level3Name')
                ic_name = d.get('insuranceCompany', {}).get('insuranceCompanyName', '')
                
                # Fetch crops
                u_crop = f"https://www.pmfby.gov.in/cropNotification/cropList?sssyID={sssy_id}&districtID={d_id}"
                crops = fetch_and_decrypt(u_crop).get('data', [])
                print(f"  District {d_name}: {len(crops)} crops. Insurer: {ic_name}")
                for c in crops[:3]:
                    c_id = c.get('cropID')
                    c_name = c.get('cropName')
                    u_calc = f"https://www.pmfby.gov.in/landingPage/calculatePremium?sssyID={sssy_id}&districtID={d_id}&cropID={c_id}"
                    p_res = fetch_and_decrypt(u_calc).get('data', [])
                    if p_res:
                        p0 = p_res[0]
                        print(f"    Crop {c_name}: PremiumRate: {p0.get('premiumRate')}% | FarmerRate: {p0.get('farmerShare')}% | SI: Rs.{p0.get('sumInsured')} | IC: {p0.get('insuranceCompanyName')}")
        except Exception as e:
            pass
