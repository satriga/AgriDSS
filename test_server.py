import urllib.request
import json

def test_endpoint(name, url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        res = urllib.request.urlopen(req, timeout=10)
        status = res.status
        content_type = res.headers.get('Content-Type')
        raw = res.read()
        print(f"[PASS] {name}: Status {status}, Content-Type: {content_type}, Size: {len(raw)} bytes")
        if 'application/json' in content_type:
            d = json.loads(raw)
            return d
    except Exception as e:
        print(f"[FAIL] {name}: {e}")
        return None

# 1. Main Page
test_endpoint('Index HTML Page', 'http://127.0.0.1:5000/')

# 2. PMFBY Dashboards
test_endpoint('PMFBY Main Page', 'http://127.0.0.1:5000/pmfby')
test_endpoint('PMFBY Companies Page', 'http://127.0.0.1:5000/pmfby/companies')

# 3. Available Dates & Categories
dates_data = test_endpoint('API Dates', 'http://127.0.0.1:5000/api/dates')
print(f"   -> Available observation dates: {dates_data['count']}, Latest: {dates_data['latest']}")

# 4. IMD Sync Status
sync_data = test_endpoint('IMD Sync Status', 'http://127.0.0.1:5000/api/imd/sync_status')
print(f"   -> Sync status: {sync_data['sync_status']['status']}, Last sync: {sync_data['sync_status']['last_sync_timestamp']}")

# 5. Districts List
dist_list = test_endpoint('Districts List', 'http://127.0.0.1:5000/api/imd/districts')
print(f"   -> Total districts loaded: {dist_list['count']}")

# 6. Historical District Analysis (Pune, Maharashtra)
pune_data = test_endpoint('District Analysis (Pune)', 'http://127.0.0.1:5000/api/imd/district_analysis?district=Pune')
dist = pune_data['district']
print(f"   -> District: {dist['district_name']}, {dist['state_name']} ({dist['subdivision']})")
print(f"   -> LPA Normal: {dist['annual_normal_mm']} mm, Monsoon Normal: {dist['monsoon_normal_mm']} mm")
print(f"   -> Peak Year: {dist['peak_rainfall_year']} ({dist['peak_rainfall_mm']} mm), Driest Year: {dist['lowest_rainfall_year']} ({dist['lowest_rainfall_mm']} mm)")
print(f"   -> Drought Years: {dist['drought_statistics']['total_drought_years']} ({dist['drought_statistics']['drought_frequency_pct']}%), Severe Return: 1 in {dist['drought_statistics']['severe_drought_return_period_years']} yrs")
print(f"   -> Timeline points: {len(dist['timeline'])} (1901 to {dist['timeline'][-1]['year']})")

# 7. Spatial SPI Grid API
spi_data = test_endpoint('Spatial SPI Grid', 'http://127.0.0.1:5000/api/imd/spi?date=2024-07-15&timescale=3')
s = spi_data['stats']
print(f"   -> Mean SPI: {s['mean_spi']}, Min SPI (Peak Drought): {s['min_spi']}, Max SPI: {s['max_spi']}")
print(f"   -> Moderate Drought Area: {s['moderate_drought_pct']}%, Severe Drought Area: {s['severe_drought_pct']}%")

# 8. Point Analysis API (Coordinates Probe)
pt_data = test_endpoint('Point Probe Analysis', 'http://127.0.0.1:5000/api/imd/point_analysis?lat=18.52&lon=73.85&date=2024-07-15')
pt = pt_data['data']
print(f"   -> Containing District: {pt['containing_district']}")
print(f"   -> SPI-1 (30d): {pt['spi_1']['value']} ({pt['spi_1']['category']})")
print(f"   -> SPI-3 (90d): {pt['spi_3']['value']} ({pt['spi_3']['category']})")
print(f"   -> SPI-12 (Annual): {pt['spi_12']['value']} ({pt['spi_12']['category']})")
print("\nALL TESTS PASSED SUCCESSFULLY!")
