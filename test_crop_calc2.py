from test_crop_calc import fetch_and_decrypt

sssy_list = fetch_and_decrypt('https://www.pmfby.gov.in/landingPage/sssyList').get('data', [])
found = 0
for s in sssy_list:
    if s.get('year') in ['2024', '2023']:
        u = f"https://www.pmfby.gov.in/landingPage/districtState?stateID={s['stateID']}&sssyID={s['sssyID']}"
        try:
            res = fetch_and_decrypt(u)
            dists = res.get('data', {}).get('hierarchy', {}).get('level3', [])
            if dists:
                st_name = s.get('sssyName', {}).get('stateName')
                d0 = dists[0]
                d_id = d0.get('level3ID')
                d_name = d0.get('level3Name')
                sssy_id = s.get('sssyID')
                print(f"{st_name} (sssy {sssy_id}): {len(dists)} dists. Sample: {d_name} ({d_id})")
                
                # Test cropList
                u_crop = f"https://www.pmfby.gov.in/cropNotification/cropList?sssyID={sssy_id}&districtID={d_id}"
                c_res = fetch_and_decrypt(u_crop)
                crops = c_res.get('data', [])
                print(f"   Crop count for {d_name}: {len(crops)}")
                if crops:
                    print("   Sample crops:", crops[:3])
                    c0 = crops[0]
                    c_id = c0.get('cropID')
                    u_calc = f"https://www.pmfby.gov.in/landingPage/calculatePremium?sssyID={sssy_id}&districtID={d_id}&cropID={c_id}"
                    prem_res = fetch_and_decrypt(u_calc)
                    print("   Calculate premium result:", prem_res)
                    found += 1
                    if found >= 3:
                        break
        except Exception as e:
            pass
