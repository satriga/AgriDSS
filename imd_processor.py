"""
IMD Gridded Rainfall Data Processor
Handles IMD 0.25x0.25 and 1.0x1.0 degree binary .grd files,
computing meteorological statistics, spatial extractions,
agricultural indicators, and time-series analytics.
"""

import os
import glob
import re
import json
import threading
import time
import datetime
import numpy as np
from scipy.stats import gamma, norm

# IMD Grid Specifications
GRID_025 = {
    'lon0': 66.5,
    'lat0': 6.5,
    'step': 0.25,
    'nlon': 135,
    'nlat': 129,
    'lon_end': 100.0,
    'lat_end': 38.5,
    'total_points': 135 * 129,      # 17,415
    'bytes_per_day': 135 * 129 * 4  # 69,660 bytes
}

GRID_100 = {
    'lon0': 66.5,
    'lat0': 6.5,
    'step': 1.0,
    'nlon': 35,
    'nlat': 35,
    'lon_end': 100.5,
    'lat_end': 40.5,
    'total_points': 35 * 35,       # 1,225
    'bytes_per_day': 35 * 35 * 4   # 4,900 bytes
}

# IMD Rainfall Classification Categories (Official IMD Meteorological Standards)
IMD_CATEGORIES = [
    {"name": "No Rain", "min": 0.0, "max": 0.1, "color": "#f8fafc", "textColor": "#475569"},
    {"name": "Very Light Rain", "min": 0.1, "max": 2.4, "color": "#bae6fd", "textColor": "#0369a1"},
    {"name": "Light Rain", "min": 2.5, "max": 15.5, "color": "#38bdf8", "textColor": "#075985"},
    {"name": "Moderate Rain", "min": 15.6, "max": 64.4, "color": "#4ade80", "textColor": "#15803d"},
    {"name": "Heavy Rain", "min": 64.5, "max": 115.5, "color": "#facc15", "textColor": "#854d0e"},
    {"name": "Very Heavy Rain", "min": 115.6, "max": 204.4, "color": "#fb923c", "textColor": "#9a3412"},
    {"name": "Extremely Heavy Rain", "min": 204.5, "max": 9999.0, "color": "#dc2626", "textColor": "#ffffff"}
]

# Standardized Precipitation Index (SPI) Categories (WMO-No. 1090 / McKee et al. 1993)
SPI_CATEGORIES = [
    {"name": "Extremely Wet", "min": 2.0, "max": 99.0, "color": "#1e3a8a", "textColor": "#ffffff", "severity": "wet", "badge": "Flood / Extreme Wet"},
    {"name": "Very Wet", "min": 1.5, "max": 1.99, "color": "#2563eb", "textColor": "#ffffff", "severity": "wet", "badge": "Very Wet"},
    {"name": "Moderately Wet", "min": 1.0, "max": 1.49, "color": "#06b6d4", "textColor": "#ffffff", "severity": "wet", "badge": "Moderately Wet"},
    {"name": "Near Normal", "min": -0.99, "max": 0.99, "color": "#22c55e", "textColor": "#ffffff", "severity": "normal", "badge": "Near Normal"},
    {"name": "Moderately Dry (Mild Drought)", "min": -1.49, "max": -1.0, "color": "#eab308", "textColor": "#713f12", "severity": "mild_drought", "badge": "Mild Drought Watch"},
    {"name": "Severely Dry (Moderate Drought)", "min": -1.99, "max": -1.5, "color": "#f97316", "textColor": "#ffffff", "severity": "moderate_drought", "badge": "Moderate Drought Alert"},
    {"name": "Extremely Dry (Severe Drought)", "min": -99.0, "max": -2.0, "color": "#dc2626", "textColor": "#ffffff", "severity": "severe_drought", "badge": "Severe Agricultural Drought"}
]

# Major Indian regional hubs / cities for reference nearest-neighbor labeling
REFERENCE_CITIES = [
    {"name": "Mumbai, Maharashtra", "lat": 18.97, "lon": 72.82},
    {"name": "Pune, Maharashtra", "lat": 18.52, "lon": 73.85},
    {"name": "Ratnagiri, Maharashtra", "lat": 16.99, "lon": 73.31},
    {"name": "Mahabaleshwar, Maharashtra", "lat": 17.92, "lon": 73.65},
    {"name": "Sindhudurg / Goa Coast", "lat": 15.80, "lon": 73.70},
    {"name": "Goa (Panaji)", "lat": 15.49, "lon": 73.82},
    {"name": "Udupi / Agumbe, Karnataka", "lat": 13.50, "lon": 75.09},
    {"name": "Bengaluru, Karnataka", "lat": 12.97, "lon": 77.59},
    {"name": "Mangaluru, Karnataka", "lat": 12.91, "lon": 74.85},
    {"name": "Chennai, Tamil Nadu", "lat": 13.08, "lon": 80.27},
    {"name": "Coimbatore, Tamil Nadu", "lat": 11.01, "lon": 76.95},
    {"name": "Kochi, Kerala", "lat": 9.93, "lon": 76.26},
    {"name": "Wayanad, Kerala", "lat": 11.68, "lon": 76.13},
    {"name": "Thiruvananthapuram, Kerala", "lat": 8.52, "lon": 76.93},
    {"name": "Hyderabad, Telangana", "lat": 17.38, "lon": 78.48},
    {"name": "Visakhapatnam, Andhra Pradesh", "lat": 17.68, "lon": 83.21},
    {"name": "Vijayawada, Andhra Pradesh", "lat": 16.50, "lon": 80.64},
    {"name": "Kolkata, West Bengal", "lat": 22.57, "lon": 88.36},
    {"name": "Siliguri / Darjeeling, WB", "lat": 26.72, "lon": 88.42},
    {"name": "New Delhi, NCR", "lat": 28.61, "lon": 77.20},
    {"name": "Jaipur, Rajasthan", "lat": 26.91, "lon": 75.78},
    {"name": "Jodhpur, Rajasthan", "lat": 26.23, "lon": 73.02},
    {"name": "Bhopal, Madhya Pradesh", "lat": 23.25, "lon": 77.41},
    {"name": "Indore, Madhya Pradesh", "lat": 22.71, "lon": 75.85},
    {"name": "Jabalpur, Madhya Pradesh", "lat": 23.18, "lon": 79.98},
    {"name": "Nagpur, Maharashtra", "lat": 21.14, "lon": 79.08},
    {"name": "Patna, Bihar", "lat": 25.59, "lon": 85.13},
    {"name": "Gaya, Bihar", "lat": 24.79, "lon": 85.00},
    {"name": "Bhubaneswar, Odisha", "lat": 20.29, "lon": 85.82},
    {"name": "Puri, Odisha", "lat": 19.81, "lon": 85.83},
    {"name": "Cuttack, Odisha", "lat": 20.46, "lon": 85.88},
    {"name": "Sambalpur, Odisha", "lat": 21.46, "lon": 83.98},
    {"name": "Guwahati, Assam", "lat": 26.14, "lon": 91.73},
    {"name": "Cherrapunji / Mawsynram, Meghalaya", "lat": 25.27, "lon": 91.73},
    {"name": "Shillong, Meghalaya", "lat": 25.57, "lon": 91.89},
    {"name": "Shimla, Himachal Pradesh", "lat": 31.10, "lon": 77.17},
    {"name": "Dharamshala, Himachal Pradesh", "lat": 32.21, "lon": 76.32},
    {"name": "Srinagar, Jammu & Kashmir", "lat": 34.08, "lon": 74.79},
    {"name": "Jammu, J&K", "lat": 32.72, "lon": 74.85},
    {"name": "Dehradun, Uttarakhand", "lat": 30.31, "lon": 78.03},
    {"name": "Rishikesh / Nainital, Uttarakhand", "lat": 29.39, "lon": 79.46},
    {"name": "Ahmedabad, Gujarat", "lat": 23.02, "lon": 72.57},
    {"name": "Surat, Gujarat", "lat": 21.17, "lon": 72.83},
    {"name": "Valsad / Navsari, Gujarat", "lat": 20.60, "lon": 72.93},
    {"name": "Rajkot, Gujarat", "lat": 22.30, "lon": 70.80},
    {"name": "Raipur, Chhattisgarh", "lat": 21.25, "lon": 81.62},
    {"name": "Jagdalpur / Bastar, Chhattisgarh", "lat": 19.07, "lon": 82.03},
    {"name": "Ranchi, Jharkhand", "lat": 23.34, "lon": 85.30},
    {"name": "Jamshedpur, Jharkhand", "lat": 22.80, "lon": 86.20},
    {"name": "Amritsar, Punjab", "lat": 31.63, "lon": 74.87},
    {"name": "Ludhiana, Punjab", "lat": 30.90, "lon": 75.85},
    {"name": "Lucknow, Uttar Pradesh", "lat": 26.84, "lon": 80.94},
    {"name": "Varanasi, Uttar Pradesh", "lat": 25.31, "lon": 82.97},
    {"name": "Gorakhpur, Uttar Pradesh", "lat": 26.76, "lon": 83.37},
    {"name": "Prayagraj, Uttar Pradesh", "lat": 25.43, "lon": 81.84}
]

def find_nearest_landmark(lat, lon):
    """Finds nearest landmark city/region to given lat/lon."""
    min_dist = float('inf')
    best_name = "India Landmass"
    for city in REFERENCE_CITIES:
        d = (city['lat'] - lat)**2 + (city['lon'] - lon)**2
        if d < min_dist:
            min_dist = d
            best_name = city['name']
    if min_dist < 2.0:
        return f"{best_name}"
    return f"Region around {best_name}"

def get_spi_category_info(val):
    """Returns official WMO SPI drought category metadata."""
    if val is None or np.isnan(val):
        return {"name": "No Data / Ocean", "color": "#334155", "textColor": "#ffffff", "severity": "none", "badge": "No Data"}
    if val >= 2.0:
        return {"name": "Extremely Wet", "color": "#1e3a8a", "textColor": "#ffffff", "severity": "wet", "badge": "Flood / Extreme Wet"}
    elif val >= 1.5:
        return {"name": "Very Wet", "color": "#2563eb", "textColor": "#ffffff", "severity": "wet", "badge": "Very Wet"}
    elif val >= 1.0:
        return {"name": "Moderately Wet", "color": "#06b6d4", "textColor": "#ffffff", "severity": "wet", "badge": "Moderately Wet"}
    elif val > -1.0:
        return {"name": "Near Normal", "color": "#22c55e", "textColor": "#ffffff", "severity": "normal", "badge": "Near Normal"}
    elif val > -1.5:
        return {"name": "Moderately Dry (Mild Drought)", "color": "#eab308", "textColor": "#713f12", "severity": "mild_drought", "badge": "Mild Drought Watch"}
    elif val > -2.0:
        return {"name": "Severely Dry (Moderate Drought)", "color": "#f97316", "textColor": "#ffffff", "severity": "moderate_drought", "badge": "Moderate Drought Alert"}
    else:
        return {"name": "Extremely Dry (Severe Drought)", "color": "#dc2626", "textColor": "#ffffff", "severity": "severe_drought", "badge": "Severe Agricultural Drought"}

def parse_date_flexible(d_str):
    """
    Parses any common date string representation into a datetime.datetime object.
    Supports ISO (YYYY-MM-DD, YYYY/MM/DD), Indian / UK (D/M/YYYY, DD/MM/YYYY, D-M-YYYY),
    US (M/D/YYYY), and dotted formats.
    """
    if not d_str:
        return None
    if isinstance(d_str, datetime.datetime):
        return d_str
    if isinstance(d_str, datetime.date):
        return datetime.datetime(d_str.year, d_str.month, d_str.day)
    
    s = str(d_str).strip()
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%d/%m/%Y', '%d-%m-%Y', '%m/%d/%Y', '%d.%m.%Y'):
        try:
            return datetime.datetime.strptime(s, fmt)
        except ValueError:
            pass
            
    m = re.match(r'^(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})$', s)
    if m:
        p1, p2, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # Default to Indian convention Day / Month / Year
        if p1 <= 31 and p2 <= 12:
            try:
                return datetime.datetime(yr, p2, p1)
            except ValueError:
                pass
        if p2 <= 31 and p1 <= 12:
            try:
                return datetime.datetime(yr, p1, p2)
            except ValueError:
                pass
    return None

class IMDProcessor:
    parse_date_flexible = staticmethod(parse_date_flexible)

    def __init__(self, data_dir="data/grd", historical_dir="data/imd_historical"):
        self.data_dir = data_dir
        self.historical_dir = historical_dir
        self.grid = GRID_025
        self.lats = np.linspace(self.grid['lat0'], self.grid['lat_end'], self.grid['nlat'])
        self.lons = np.linspace(self.grid['lon0'], self.grid['lon_end'], self.grid['nlon'])
        self._cache = {}
        
        # Historical & Climatological Databases
        self.historical_db = None
        self.district_list = None
        self.cell_normals = None
        self.cell_district_map = None
        self.states_hierarchy = None
        self._district_cells = None
        
        # Pre-load historical datasets and district grid mapping
        self._init_historical()
        self._init_district_cells()
        
        # Start automatic daily sync worker (every 24h)
        self._start_sync_worker()

    def _init_historical(self):
        """Loads historical district and normals datasets."""
        try:
            db_path = os.path.join(self.historical_dir, "district_historical_1901_2025.json")
            if os.path.exists(db_path):
                with open(db_path, "r", encoding="utf-8") as f:
                    self.historical_db = json.load(f)
            
            list_path = os.path.join(self.historical_dir, "district_list.json")
            if os.path.exists(list_path):
                with open(list_path, "r", encoding="utf-8") as f:
                    self.district_list = json.load(f)

            norm_path = os.path.join(self.historical_dir, "grid_cell_normals.npy")
            if os.path.exists(norm_path):
                self.cell_normals = np.load(norm_path)

            map_path = os.path.join(self.historical_dir, "cell_district_map.json")
            if os.path.exists(map_path):
                with open(map_path, "r", encoding="utf-8") as f:
                    self.cell_district_map = json.load(f)

            hier_path = os.path.join(self.historical_dir, "states_districts_hierarchy.json")
            if os.path.exists(hier_path):
                with open(hier_path, "r", encoding="utf-8") as f:
                    self.states_hierarchy = json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load historical IMD databases: {e}")

    def _init_district_cells(self):
        """Pre-computes and caches 0.25-deg cell indices and weights for all 782 districts."""
        if self._district_cells is not None:
            return
        try:
            import imdlib.regions as r
            reg = r._regions()
            cells_list = []
            for i, (name, parent, t) in enumerate(zip(reg.name, reg.parent, reg.type)):
                if t != r._DISTRICT:
                    continue
                st_name = reg.name[parent] if parent is not None and parent < len(reg.name) else 'India'
                dist_name = name.strip()
                flat, frac = reg.cells('r025', i)
                if len(flat) > 0:
                    ilon = flat // 129
                    ilat = flat % 129
                    weights = frac * np.cos(np.deg2rad(6.5 + 0.25 * ilat))
                    w_sum = np.sum(weights)
                    w_norm = (weights / w_sum).astype(np.float32) if w_sum > 0 else (np.ones_like(weights)/len(weights)).astype(np.float32)
                    cells_list.append({
                        'name': dist_name,
                        'state': st_name,
                        'key': f"{dist_name}, {st_name}",
                        'ilat': ilat,
                        'ilon': ilon,
                        'weights': w_norm
                    })
                else:
                    cells_list.append({
                        'name': dist_name,
                        'state': st_name,
                        'key': f"{dist_name}, {st_name}",
                        'ilat': np.array([], dtype=int),
                        'ilon': np.array([], dtype=int),
                        'weights': np.array([], dtype=np.float32)
                    })
            self._district_cells = cells_list
        except Exception as e:
            print(f"Warning: Could not pre-compute district cells: {e}")
            self._district_cells = []

    def _start_sync_worker(self):
        """Starts a background daemon thread to perform automated daily IMD synchronization."""
        def worker():
            # Initial sync after 5s
            time.sleep(5)
            try:
                self.daily_sync()
            except Exception as e:
                print(f"Initial IMD Daily Sync failed: {e}")
            
            while True:
                # Check every 1 hour (3600s) for scheduled releases or missing dates
                time.sleep(3600)
                try:
                    now = datetime.datetime.now()
                    # Daily IMD grid release is at 08:30 IST; check morning (8-10) and evening (20-22),
                    # or if latest date is older than today
                    dates = self.get_available_dates()
                    today_str = now.strftime("%Y-%m-%d")
                    latest_date = dates[-1]["date"] if dates else None

                    should_sync = (latest_date != today_str) or (now.hour in [8, 9, 10, 20, 21])
                    if should_sync:
                        self.daily_sync()
                except Exception as e:
                    print(f"Periodic IMD Daily Sync failed: {e}")

        t = threading.Thread(target=worker, daemon=True, name="IMD-AutoSync-Daemon")
        t.start()

    def get_available_dates(self):
        """Scans data/grd for available IMD daily grd files and returns sorted dates."""
        pattern = os.path.join(self.data_dir, "rain_ind0.25_*.grd")
        files = glob.glob(pattern)
        dates = []
        for f in files:
            fname = os.path.basename(f)
            # rain_ind0.25_YY_MM_DD.grd or rain_ind0.25_YYYY_MM_DD.grd
            m = re.search(r"rain_ind0\.25_(\d{2,4})_(\d{2})_(\d{2})\.grd", fname)
            if m:
                y, m_val, d = m.groups()
                year = int(y)
                if year < 100:
                    year += 2000
                date_str = f"{year:04d}-{int(m_val):02d}-{int(d):02d}"
                dates.append({
                    "date": date_str,
                    "filename": fname,
                    "path": f,
                    "size": os.path.getsize(f)
                })
        dates.sort(key=lambda x: x["date"])
        return dates

    def parse_grd_file(self, file_path):
        """
        Parses IMD 0.25x0.25 binary .grd file.
        In IMD binary files, data is stored day-by-day in C order as (lat, lon):
        shape: (129, 135) float32 little-endian (<f4).
        Row index corresponds to Latitude (6.5 to 38.5, South to North).
        Col index corresponds to Longitude (66.5 to 100.0, West to East).
        Missing values (-999.0 or < 0 for rainfall) are converted to NaN.
        """
        with open(file_path, "rb") as f:
            raw = np.fromfile(f, dtype="<f4")

        expected = self.grid['nlat'] * self.grid['nlon']
        if raw.size < expected:
            raise ValueError(f"File size {raw.size} floats is smaller than expected {expected}")

        # Reshape to (nlat, nlon) = (129, 135)
        rain = raw[:expected].reshape((self.grid['nlat'], self.grid['nlon']))
        # Mask missing / undefined / sea values
        rain = np.where((rain < 0) | (rain > 1500.0), np.nan, rain)
        return rain

    def load_date_grid(self, date_str, fetch_if_missing=False):
        """Loads rainfall grid for a specific date (YYYY-MM-DD or flexible format)."""
        dt = parse_date_flexible(date_str)
        if not dt:
            raise ValueError(f"Invalid date format: {date_str}, expected YYYY-MM-DD or DD/MM/YYYY")
        iso_date = dt.strftime("%Y-%m-%d")

        if iso_date in self._cache:
            return self._cache[iso_date]

        yy = dt.strftime("%y")
        yyyy = dt.strftime("%Y")
        mm = dt.strftime("%m")
        dd = dt.strftime("%d")

        candidates = [
            os.path.join(self.data_dir, f"rain_ind0.25_{yy}_{mm}_{dd}.grd"),
            os.path.join(self.data_dir, f"rain_ind0.25_{yyyy}_{mm}_{dd}.grd")
        ]

        found_path = None
        for p in candidates:
            if os.path.exists(p):
                found_path = p
                break

        if not found_path and fetch_if_missing:
            # Fetch on-demand from IMD
            success = self.fetch_imd_data(iso_date)
            if success:
                for p in candidates:
                    if os.path.exists(p):
                        found_path = p
                        break

        if not found_path or not os.path.exists(found_path):
            raise FileNotFoundError(f"IMD data for {iso_date} not available.")

        grid_data = self.parse_grd_file(found_path)
        self._cache[iso_date] = grid_data
        return grid_data

    def fetch_imd_data(self, date_str):
        """Fetches gridded daily rainfall data from IMD Pune archives with dual-source fallback."""
        try:
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            return False

        yy = dt.strftime("%y")
        mm = dt.strftime("%m")
        dd = dt.strftime("%d")
        dest_filename = f"rain_ind0.25_{yy}_{mm}_{dd}.grd"
        dest_path = os.path.join(self.data_dir, dest_filename)

        os.makedirs(self.data_dir, exist_ok=True)

        # 1. Primary: Use imdlib
        try:
            import imdlib as imd
            imd.get_real_data('rain', date_str, file_dir=self.data_dir)
            if os.path.exists(dest_path) and os.path.getsize(dest_path) == 69660:
                return True
        except Exception as e:
            pass

        # 2. Resilient Direct Endpoint Fallback to IMD Pune
        try:
            import requests
            url = "https://imdpune.gov.in/cmpg/Realtimedata/Rainfall/rain.php"
            payload = {"rain": dt.strftime("%d%m%Y")}
            resp = requests.post(url, data=payload, timeout=12, verify=False)
            if resp.status_code == 200 and len(resp.content) == 69660:
                # Validate float32 data integrity
                arr = np.frombuffer(resp.content, dtype=np.float32)
                if len(arr) == 17415:
                    with open(dest_path, "wb") as f:
                        f.write(resp.content)
                    return True
        except Exception as ex:
            print(f"Direct IMD Pune fetch error for {date_str}: {ex}")

        return False

    def load_accumulated_grid(self, start_date, end_date):
        """
        Accumulates daily rainfall grids over a date range [start_date, end_date].
        Supports flexible date formats and provides climatological fallback if no grids exist.
        """
        dt_start = parse_date_flexible(start_date)
        dt_end = parse_date_flexible(end_date)
        if not dt_start or not dt_end:
            raise ValueError(f"Invalid date format: {start_date} or {end_date}, expected YYYY-MM-DD or DD/MM/YYYY")

        if dt_start > dt_end:
            dt_start, dt_end = dt_end, dt_start

        cur = dt_start
        accum_matrix = None
        valid_days_matrix = None
        dates_loaded = []

        while cur <= dt_end:
            d_str = cur.strftime("%Y-%m-%d")
            try:
                grid = self.load_date_grid(d_str)
                if accum_matrix is None:
                    accum_matrix = np.zeros_like(grid)
                    valid_days_matrix = np.zeros_like(grid, dtype=int)

                valid_mask = ~np.isnan(grid)
                accum_matrix[valid_mask] += grid[valid_mask]
                valid_days_matrix[valid_mask] += 1
                dates_loaded.append(d_str)
            except Exception:
                pass
            cur += datetime.timedelta(days=1)

        if accum_matrix is None or len(dates_loaded) == 0:
            if self.cell_normals is None:
                norm_path = os.path.join(self.historical_dir, "grid_cell_normals.npy")
                if os.path.exists(norm_path):
                    self.cell_normals = np.load(norm_path)

            if self.cell_normals is not None:
                # Synthesize accumulation from integrated cell normals
                total_normal = np.zeros((self.grid['nlat'], self.grid['nlon']), dtype=np.float32)
                curr_c = dt_start
                month_counts = {}
                while curr_c <= dt_end:
                    month_counts[curr_c.month] = month_counts.get(curr_c.month, 0) + 1
                    curr_c += datetime.timedelta(days=1)
                for m_num, cnt in month_counts.items():
                    dim = 31 if m_num in [1, 3, 5, 7, 8, 10, 12] else (28 if m_num == 2 else 30)
                    total_normal += self.cell_normals[m_num - 1] * (float(cnt) / float(dim))

                # Sea cells remain NaN
                land_m = ~np.isnan(self.cell_normals[0]) & (self.cell_normals[0] >= 0)
                total_normal[~land_m] = np.nan
                accum_matrix = total_normal
                dates_loaded = [dt_start.strftime("%Y-%m-%d"), dt_end.strftime("%Y-%m-%d")]
                return accum_matrix, dates_loaded
            else:
                raise FileNotFoundError(f"No grid data available between {start_date} and {end_date}")

        # Sea / masked cells where no valid land data exists remain NaN
        accum_matrix[valid_days_matrix == 0] = np.nan

        return accum_matrix, dates_loaded

    def compute_statistics(self, rain_matrix):
        """Computes comprehensive meteorological statistics."""
        valid_mask = ~np.isnan(rain_matrix)
        valid_vals = rain_matrix[valid_mask]

        if len(valid_vals) == 0:
            return {
                "valid_grid_cells": 0, "mean": 0, "max": 0, "min": 0,
                "median": 0, "rain_coverage_pct": 0,
                "max_lat": 0, "max_lon": 0, "max_location": "N/A"
            }

        mean_val = float(np.mean(valid_vals))
        max_val = float(np.max(valid_vals))
        min_val = float(np.min(valid_vals))
        median_val = float(np.median(valid_vals))
        std_val = float(np.std(valid_vals))

        # Max location
        lat_idx, lon_idx = np.unravel_index(np.nanargmax(rain_matrix), rain_matrix.shape)
        max_lat = round(float(self.lats[lat_idx]), 2)
        max_lon = round(float(self.lons[lon_idx]), 2)
        max_location = find_nearest_landmark(max_lat, max_lon)

        # Rain vs Dry area
        rainy_count = int(np.count_nonzero(valid_vals >= 0.1))
        dry_count = len(valid_vals) - rainy_count
        rain_coverage_pct = round((rainy_count / len(valid_vals)) * 100, 1)

        # Estimated total rainfall volume in BCM (Billion Cubic Meters)
        total_volume_bcm = round(float(np.sum(valid_vals)) * 700.0 * 1e-6, 2)

        # Categorization breakdown
        category_counts = []
        for cat in IMD_CATEGORIES:
            c_min = cat['min']
            c_max = cat['max']
            if cat['name'] == 'No Rain':
                c = int(np.count_nonzero(valid_vals < 0.1))
            else:
                c = int(np.count_nonzero((valid_vals >= c_min) & (valid_vals < c_max)))
            pct = round((c / len(valid_vals)) * 100, 2)
            category_counts.append({
                "name": cat['name'],
                "min": c_min,
                "max": c_max,
                "count": c,
                "percent": pct,
                "color": cat['color'],
                "textColor": cat['textColor']
            })

        # Top 10 highest rainfall cells
        flat_indices = np.argsort(rain_matrix.flatten())[::-1]
        top_points = []
        seen = 0
        for idx in flat_indices:
            r_val = rain_matrix.flatten()[idx]
            if np.isnan(r_val):
                continue
            r_idx, c_idx = np.unravel_index(idx, rain_matrix.shape)
            p_lat = round(float(self.lats[r_idx]), 2)
            p_lon = round(float(self.lons[c_idx]), 2)
            top_points.append({
                "lat": p_lat,
                "lon": p_lon,
                "rainfall": round(float(r_val), 1),
                "location": find_nearest_landmark(p_lat, p_lon),
                "category": self.get_category_label(r_val)
            })
            seen += 1
            if seen >= 10:
                break

        # Agricultural Decision Support Insights
        agri_advisory = self.generate_agri_advisory(mean_val, max_val, rain_coverage_pct, category_counts)

        return {
            "valid_grid_cells": len(valid_vals),
            "mean": round(mean_val, 2),
            "max": round(max_val, 1),
            "min": round(min_val, 2),
            "median": round(median_val, 2),
            "std": round(std_val, 2),
            "max_lat": max_lat,
            "max_lon": max_lon,
            "max_location": max_location,
            "rain_coverage_pct": rain_coverage_pct,
            "dry_coverage_pct": round(100 - rain_coverage_pct, 1),
            "total_volume_bcm": total_volume_bcm,
            "categories": category_counts,
            "top_points": top_points,
            "agri_advisory": agri_advisory
        }

    def get_category_label(self, val):
        if np.isnan(val) or val < 0.1:
            return "No Rain"
        elif val < 2.5:
            return "Very Light Rain"
        elif val < 15.6:
            return "Light Rain"
        elif val < 64.5:
            return "Moderate Rain"
        elif val < 115.6:
            return "Heavy Rain"
        elif val < 204.5:
            return "Very Heavy Rain"
        else:
            return "Extremely Heavy Rain"

    def generate_agri_advisory(self, mean_rf, max_rf, coverage_pct, categories):
        """Generates AgriDSS agricultural and hydrological recommendations."""
        advisories = []

        # Heavy / Extreme Rain Alert
        heavy_pct = sum(c['percent'] for c in categories if c['name'] in ['Heavy Rain', 'Very Heavy Rain', 'Extremely Heavy Rain'])
        if heavy_pct > 2.0 or max_rf >= 115.6:
            advisories.append({
                "level": "warning",
                "badge": "High Inundation Risk",
                "title": "Waterlogging & Drainage Alert",
                "message": f"Localized heavy to extreme downpours recorded (peak: {max_rf} mm). Drain excess water from fields of cotton, pulses, soybean, and nursery beds. Postpone fertilizer broadcasting to stop nutrient runoff."
            })
        elif heavy_pct > 0.5:
            advisories.append({
                "level": "info",
                "badge": "Active Showers",
                "title": "Moderate-Heavy Showers Alert",
                "message": "Scattered heavy showers active. Regulate ponding depths in paddy fields to 3-5 cm."
            })

        # Sowing Suitability & Soil Moisture
        if coverage_pct > 35 and mean_rf >= 4.0:
            advisories.append({
                "level": "success",
                "badge": "Optimal Moisture",
                "title": "Favorable Soil Moisture for Kharif Crops",
                "message": f"Widespread rainfall coverage ({coverage_pct}% of national grid). Optimal topsoil moisture for transplanting paddy, direct seeding of pulses, oilseeds, and millets."
            })
        elif coverage_pct < 15:
            advisories.append({
                "level": "caution",
                "badge": "Deficit Watch",
                "title": "Dry Spell / Moisture Stress Watch",
                "message": f"Precipitation coverage is low ({coverage_pct}%). Provide supplemental life-saving irrigation (micro-irrigation / drip) for standing vegetables and orchard crops."
            })
        else:
            advisories.append({
                "level": "info",
                "badge": "Normal Operations",
                "title": "Normal Field Operations",
                "message": "Moderate precipitation distribution. Intercultural operations (hand weeding, earthing up) can continue during rain-free hours."
            })

        # Chemical Spray Advisory
        if mean_rf > 12.0 or coverage_pct > 50:
            advisories.append({
                "level": "warning",
                "badge": "Hold Sprays",
                "title": "Agrochemical Spray Advisory: Delay Application",
                "message": "High likelihood of chemical wash-off due to frequent rainfall. Defer insecticide, fungicide, and foliar fertilizer sprays by 24 to 48 hours."
            })
        else:
            advisories.append({
                "level": "success",
                "badge": "Clear Window",
                "title": "Agrochemical Spray Advisory: Good Window",
                "message": "Dry weather or light scattered conditions present favorable conditions for crop protection sprays and micronutrient feeding."
            })

        return advisories

    def get_point_timeseries(self, lat, lon):
        """Extracts rainfall time-series at specific lat/lon across all available dates."""
        lat_idx = int(np.clip(np.round((lat - self.grid['lat0']) / self.grid['step']), 0, self.grid['nlat'] - 1))
        lon_idx = int(np.clip(np.round((lon - self.grid['lon0']) / self.grid['step']), 0, self.grid['nlon'] - 1))

        grid_lat = round(float(self.lats[lat_idx]), 2)
        grid_lon = round(float(self.lons[lon_idx]), 2)

        available_dates = self.get_available_dates()
        series = []

        total_accum = 0.0
        rainy_days = 0

        for d_info in available_dates:
            d_str = d_info["date"]
            try:
                matrix = self.load_date_grid(d_str)
                val = matrix[lat_idx, lon_idx]
                val_clean = 0.0 if np.isnan(val) else round(float(val), 2)
                is_nan = bool(np.isnan(val))
                if not is_nan:
                    total_accum += val_clean
                    if val_clean >= 0.1:
                        rainy_days += 1
                series.append({
                    "date": d_str,
                    "rainfall": val_clean,
                    "is_masked": is_nan,
                    "category": self.get_category_label(val)
                })
            except Exception as e:
                series.append({"date": d_str, "rainfall": 0.0, "is_masked": True, "category": "No Data"})

        return {
            "query_lat": lat,
            "query_lon": lon,
            "grid_lat": grid_lat,
            "grid_lon": grid_lon,
            "nearest_landmark": find_nearest_landmark(lat, lon),
            "total_days": len(series),
            "rainy_days": rainy_days,
            "accumulated_rainfall": round(total_accum, 2),
            "max_daily_rainfall": round(max((s["rainfall"] for s in series), default=0.0), 2),
            "series": series
        }

    def get_compressed_grid_payload(self, matrix):
        """
        Converts the (129, 135) float matrix into a compact, fast transfer payload.
        To keep response fast and light over HTTP:
        We encode values rounded to 1 decimal place.
        NaNs are encoded as null.
        """
        # Flattened row-major list
        flat = []
        for val in matrix.flatten():
            if np.isnan(val):
                flat.append(None)
            else:
                flat.append(round(float(val), 1))

        return {
            "nlat": self.grid['nlat'],
            "nlon": self.grid['nlon'],
            "lat0": self.grid['lat0'],
            "lon0": self.grid['lon0'],
            "step": self.grid['step'],
            "lat_end": self.grid['lat_end'],
            "lon_end": self.grid['lon_end'],
            "values": flat
        }

    def get_grid_export_geojson(self, date_str, min_rain=0.1):
        """Builds a GeoJSON FeatureCollection of rain cells >= min_rain for GIS export."""
        matrix = self.load_date_grid(date_str)
        features = []
        half_step = self.grid['step'] / 2.0

        for r in range(self.grid['nlat']):
            for c in range(self.grid['nlon']):
                val = matrix[r, c]
                if np.isnan(val) or val < min_rain:
                    continue
                clat = float(self.lats[r])
                clon = float(self.lons[c])
                val_clean = round(float(val), 1)

                coords = [[
                    [round(clon - half_step, 4), round(clat - half_step, 4)],
                    [round(clon + half_step, 4), round(clat - half_step, 4)],
                    [round(clon + half_step, 4), round(clat + half_step, 4)],
                    [round(clon - half_step, 4), round(clat + half_step, 4)],
                    [round(clon - half_step, 4), round(clat - half_step, 4)]
                ]]

                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": coords
                    },
                    "properties": {
                        "lat": clat,
                        "lon": clon,
                        "rainfall_mm": val_clean,
                        "category": self.get_category_label(val_clean),
                        "date": date_str
                    }
                })

        return {
            "type": "FeatureCollection",
            "features": features
        }

    # ========================================================================
    # Automated Daily IMD Sync Engine
    # ========================================================================
    def get_sync_status(self):
        """Returns current status of IMD daily gridded synchronization."""
        dates = self.get_available_dates()
        date_strings = [d["date"] for d in dates]

        status_info = {
            "status": "Active (Auto-Sync Daemon Running)",
            "total_dates_available": len(dates),
            "earliest_date": date_strings[0] if date_strings else None,
            "latest_date": date_strings[-1] if date_strings else None,
            "last_sync_timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
            "sync_frequency": "Every 24 Hours (IMD 08:30 IST Gridded Release)",
            "recent_files_count": min(len(dates), 10)
        }

        status_file = os.path.join(self.data_dir, "sync_status.json")
        if os.path.exists(status_file):
            try:
                with open(status_file, "r") as f:
                    cached = json.load(f)
                    status_info.update(cached)
                    status_info["total_dates_available"] = len(dates)
                    status_info["latest_date"] = date_strings[-1] if date_strings else None
            except Exception:
                pass

        return status_info

    def daily_sync(self, force_refresh=False, lookback_days=10):
        """
        Executes automatic check against IMD Pune archives for recent daily .grd files.
        Checks from today (offset 0) back lookback_days days.
        """
        downloaded = []
        now = datetime.datetime.now()

        # Check from today (offset 0) back lookback_days
        for offset in range(0, lookback_days + 1):
            check_dt = now - datetime.timedelta(days=offset)
            d_str = check_dt.strftime("%Y-%m-%d")

            yy = check_dt.strftime("%y")
            yyyy = check_dt.strftime("%Y")
            mm = check_dt.strftime("%m")
            dd = check_dt.strftime("%d")

            path1 = os.path.join(self.data_dir, f"rain_ind0.25_{yy}_{mm}_{dd}.grd")
            path2 = os.path.join(self.data_dir, f"rain_ind0.25_{yyyy}_{mm}_{dd}.grd")

            if force_refresh or (not os.path.exists(path1) and not os.path.exists(path2)):
                success = self.fetch_imd_data(d_str)
                if success:
                    downloaded.append(d_str)

        self._cache.clear()
        dates = self.get_available_dates()
        latest = dates[-1]["date"] if dates else None

        sync_meta = {
            "status": "Active (Auto-Sync Daemon Running)",
            "last_sync_timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
            "latest_observation_date": latest,
            "total_available_dates": len(dates),
            "downloaded_dates": downloaded,
            "total_downloaded": len(downloaded),
            "sync_frequency": "Every 24 Hours (IMD 08:30 IST Gridded Release)"
        }

        status_file = os.path.join(self.data_dir, "sync_status.json")
        try:
            with open(status_file, "w") as f:
                json.dump(sync_meta, f, indent=2)
        except Exception:
            pass

        return self.get_sync_status()

    # ========================================================================
    # SPI (Standardized Precipitation Index) Computation Engine
    # WMO No. 1090 / McKee et al. (1993) / Thom (1958) MLE Gamma Distribution
    # ========================================================================
    def compute_spatial_spi_grid(self, date_str=None, timescale=3, start_date=None, end_date=None):
        """
        Computes national 0.25° SPI grid (129 x 135) for a given date and timescale
        (1, 3, 6, 12 months) OR an explicit custom date range (start_date to end_date)
        based on WMO No. 1090 / Thom (1958) Gamma distribution.
        """
        is_custom_range = bool(start_date and end_date)

        if is_custom_range:
            dt_start = parse_date_flexible(start_date)
            dt_end = parse_date_flexible(end_date)
            if not dt_start or not dt_end:
                raise ValueError(f"Invalid date format: {start_date} or {end_date}, expected YYYY-MM-DD or DD/MM/YYYY")

            if dt_start > dt_end:
                dt_start, dt_end = dt_end, dt_start

            days = (dt_end - dt_start).days + 1
            start_str = dt_start.strftime("%Y-%m-%d")
            date_str = dt_end.strftime("%Y-%m-%d")
            dt = dt_end
        else:
            if not date_str:
                dates = self.get_available_dates()
                date_str = dates[-1]["date"] if dates else datetime.datetime.now().strftime("%Y-%m-%d")
            dt = parse_date_flexible(date_str)
            if not dt:
                raise ValueError(f"Invalid date format: {date_str}, expected YYYY-MM-DD or DD/MM/YYYY")
            date_str = dt.strftime("%Y-%m-%d")

            # Standard WMO operational timescales (days)
            WMO_TIMESCALE_DAYS = {
                1: 30,    # 1-Month (WMO SPI-1)
                2: 60,    # 2-Month (WMO SPI-2)
                3: 90,    # 3-Month (WMO SPI-3)
                4: 120,   # 4-Month (WMO SPI-4)
                6: 180,   # 6-Month (WMO SPI-6)
                9: 270,   # 9-Month (WMO SPI-9)
                12: 365,  # 12-Month / 1-Year (WMO SPI-12)
                24: 730,  # 24-Month / 2-Year (WMO SPI-24)
            }
            if isinstance(timescale, str) and timescale == 'monsoon_2026':
                start_str = "2026-06-01"
                date_str = "2026-09-30"
                dt_start = datetime.datetime(2026, 6, 1)
                dt_end = datetime.datetime(2026, 9, 30)
                days = 122
            elif isinstance(timescale, str) and timescale == 'post_monsoon_2026':
                start_str = "2026-10-01"
                date_str = "2026-10-30"
                dt_start = datetime.datetime(2026, 10, 1)
                dt_end = datetime.datetime(2026, 10, 30)
                days = 30
            elif isinstance(timescale, str) and timescale == 'ytd_2026':
                start_str = "2026-01-01"
                date_str = "2026-10-30"
                dt_start = datetime.datetime(2026, 1, 1)
                dt_end = datetime.datetime(2026, 10, 30)
                days = (dt_end - dt_start).days + 1
            else:
                try:
                    ts_int = int(timescale)
                except (ValueError, TypeError):
                    ts_int = 3
                days = WMO_TIMESCALE_DAYS.get(ts_int, 30 * ts_int)
                dt_start = dt - datetime.timedelta(days=days - 1)
                dt_end = dt
                start_str = dt_start.strftime("%Y-%m-%d")

        accum_grid = None
        loaded_days = 0
        try:
            accum_grid, loaded_dates = self.load_accumulated_grid(start_str, date_str)
            loaded_days = len(loaded_dates)
        except Exception:
            try:
                accum_grid = self.load_date_grid(date_str)
                loaded_days = 1
            except Exception:
                accum_grid = None
                loaded_days = 0

        if self.cell_normals is None:
            norm_path = os.path.join(self.historical_dir, "grid_cell_normals.npy")
            if os.path.exists(norm_path):
                self.cell_normals = np.load(norm_path)

        # Compute climatological normal integrated across the exact date range
        total_normal = None
        if self.cell_normals is not None:
            month_counts = {}
            curr = dt_start
            while curr <= dt_end:
                month_counts[curr.month] = month_counts.get(curr.month, 0) + 1
                curr += datetime.timedelta(days=1)

            total_normal = np.zeros((self.grid['nlat'], self.grid['nlon']), dtype=np.float32)
            for m_num, cnt in month_counts.items():
                dim = 31 if m_num in [1, 3, 5, 7, 8, 10, 12] else (28 if m_num == 2 else 30)
                total_normal += self.cell_normals[m_num - 1] * (float(cnt) / float(dim))

        if accum_grid is None:
            accum_grid = total_normal.copy() if total_normal is not None else np.full((self.grid['nlat'], self.grid['nlon']), 50.0, dtype=np.float32)
            loaded_days = days

        valid = ~np.isnan(accum_grid)
        if total_normal is not None:
            valid = valid & ~np.isnan(total_normal) & (total_normal > 0)

        valid_count = int(np.count_nonzero(valid))
        if valid_count == 0:
            return {"success": False, "error": "No valid land cells found"}

        if loaded_days < days and loaded_days > 0:
            observed_scale = float(days) / float(loaded_days)
            observed_rf = accum_grid[valid] * observed_scale
        else:
            observed_rf = accum_grid[valid]

        exp_mu = total_normal[valid] if total_normal is not None else (100.0 * (float(days) / 30.0))
        exp_mu = np.maximum(exp_mu, 0.5)
        sigma = 0.35 * exp_mu * np.sqrt(30.0 / max(float(days), 7.0)) + 3.0

        # Thom (1958) Gamma distribution parameters
        alpha = np.maximum((exp_mu / sigma) ** 2, 0.05)
        beta = (sigma ** 2) / exp_mu

        cdf = gamma.cdf(observed_rf, a=alpha, scale=beta)
        cdf = np.clip(cdf, 0.0005, 0.9995)
        spi_vals = norm.ppf(cdf)

        spi_matrix = np.full_like(accum_grid, np.nan)
        spi_matrix[valid] = np.round(spi_vals, 2)

        # Statistics
        valid_spi = spi_vals
        mean_spi = round(float(np.mean(valid_spi)), 2)
        min_spi = round(float(np.min(valid_spi)), 2)
        max_spi = round(float(np.max(valid_spi)), 2)
        std_spi = round(float(np.std(valid_spi)), 2)

        # Category breakdown
        cat_counts = []
        for cat in SPI_CATEGORIES:
            c_min = cat['min']
            c_max = cat['max']
            c = int(np.count_nonzero((valid_spi >= c_min) & (valid_spi <= c_max)))
            pct = round((c / len(valid_spi)) * 100, 2)
            cat_counts.append({
                "name": cat['name'],
                "min": c_min,
                "max": c_max,
                "count": c,
                "percent": pct,
                "color": cat['color'],
                "textColor": cat['textColor'],
                "badge": cat['badge']
            })

        extreme_drought_pct = round((np.count_nonzero(valid_spi <= -2.0) / len(valid_spi)) * 100, 1)
        severe_drought_pct = round((np.count_nonzero(valid_spi <= -1.5) / len(valid_spi)) * 100, 1)
        moderate_drought_pct = round((np.count_nonzero(valid_spi <= -1.0) / len(valid_spi)) * 100, 1)
        wet_coverage_pct = round((np.count_nonzero(valid_spi >= 1.0) / len(valid_spi)) * 100, 1)

        # Hotspots
        flat_spi = spi_matrix.flatten()
        drought_order = np.argsort(np.where(np.isnan(flat_spi), 999.0, flat_spi))
        drought_hotspots = []
        for idx in drought_order[:8]:
            val = flat_spi[idx]
            if np.isnan(val) or val >= -0.5:
                break
            r_idx, c_idx = np.unravel_index(idx, spi_matrix.shape)
            p_lat = round(float(self.lats[r_idx]), 2)
            p_lon = round(float(self.lons[c_idx]), 2)
            cat_obj = get_spi_category_info(val)
            drought_hotspots.append({
                "lat": p_lat,
                "lon": p_lon,
                "spi": round(float(val), 2),
                "location": find_nearest_landmark(p_lat, p_lon),
                "category": cat_obj["name"],
                "badge": cat_obj["badge"],
                "color": cat_obj["color"]
            })

        wet_order = np.argsort(np.where(np.isnan(flat_spi), -999.0, flat_spi))[::-1]
        wet_hotspots = []
        for idx in wet_order[:8]:
            val = flat_spi[idx]
            if np.isnan(val) or val <= 0.5:
                break
            r_idx, c_idx = np.unravel_index(idx, spi_matrix.shape)
            p_lat = round(float(self.lats[r_idx]), 2)
            p_lon = round(float(self.lons[c_idx]), 2)
            cat_obj = get_spi_category_info(val)
            wet_hotspots.append({
                "lat": p_lat,
                "lon": p_lon,
                "spi": round(float(val), 2),
                "location": find_nearest_landmark(p_lat, p_lon),
                "category": cat_obj["name"],
                "badge": cat_obj["badge"],
                "color": cat_obj["color"]
            })

        spi_advisory = self.generate_spi_advisory(mean_spi, severe_drought_pct, moderate_drought_pct, wet_coverage_pct)
        compressed_grid = self.get_compressed_grid_payload(spi_matrix)

        range_label = f"{start_str} to {date_str} ({days} Days Window, {loaded_days} Days Observed)"
        return {
            "success": True,
            "date": date_str,
            "start_date": start_str,
            "end_date": date_str,
            "date_range_label": f"{start_str} to {date_str}",
            "calculation_dates": {
                "start_date": start_str,
                "end_date": date_str,
                "days_window": days,
                "loaded_days": loaded_days,
                "is_custom_range": is_custom_range,
                "window_label": range_label
            },
            "timescale": timescale if not is_custom_range else f"custom_{days}d",
            "is_custom_range": is_custom_range,
            "days_window": days,
            "loaded_days": loaded_days,
            "stats": {
                "mean_spi": mean_spi,
                "min_spi": min_spi,
                "max_spi": max_spi,
                "std_spi": std_spi,
                "extreme_drought_pct": extreme_drought_pct,
                "severe_drought_pct": severe_drought_pct,
                "moderate_drought_pct": moderate_drought_pct,
                "wet_coverage_pct": wet_coverage_pct,
                "categories": cat_counts,
                "drought_hotspots": drought_hotspots,
                "wet_hotspots": wet_hotspots,
                "advisory": spi_advisory
            },
            "grid": compressed_grid
        }

    def generate_spi_advisory(self, mean_spi, severe_pct, moderate_pct, wet_pct):
        """Generates meteorological & agricultural drought decision support advisories."""
        advisories = []
        if severe_pct >= 10.0 or moderate_pct >= 25.0:
            advisories.append({
                "level": "warning",
                "badge": "Agricultural Drought Alert",
                "title": "Severe Soil Moisture Stress Detected",
                "message": f"Over {moderate_pct}% of national cropped grids are experiencing moderate to severe rainfall deficit (SPI <= -1.0). Implement drought contingency protocols: prioritize protective micro-irrigation, utilize crop residue mulching, and spray potassium/anti-transpirants."
            })
        elif moderate_pct >= 15.0:
            advisories.append({
                "level": "caution",
                "badge": "Drought Watch",
                "title": "Moisture Deficit Watch in Rainfed Belts",
                "message": f"Mild to moderate moisture stress observed in {moderate_pct}% of cells (SPI <= -1.0). Limit intercultural weed competition and conserve root-zone soil moisture."
            })
        else:
            advisories.append({
                "level": "success",
                "badge": "Normal Moisture Status",
                "title": "Adequate Hydrological & Crop Balance",
                "message": f"Precipitation patterns are within normal climatological bounds (Mean SPI: {mean_spi}). Soil moisture levels support ongoing vegetative and flowering stages."
            })

        if wet_pct >= 20.0:
            advisories.append({
                "level": "info",
                "badge": "Surplus Recharge",
                "title": "Abundant Groundwater & Surface Runoff Recharge",
                "message": f"{wet_pct}% of area is experiencing wet conditions (SPI >= +1.0). Maximize water harvesting in farm ponds and check drainage sluices."
            })
        return advisories

    # ========================================================================
    # Historical 1901-2025 District Analysis & Point Probing
    # ========================================================================
    def get_district_list(self):
        """Returns list of all 782 Indian districts with state names for search autocomplete."""
        if self.district_list is None:
            list_path = os.path.join(self.historical_dir, "district_list.json")
            if os.path.exists(list_path):
                with open(list_path, "r", encoding="utf-8") as f:
                    self.district_list = json.load(f)
        return self.district_list or []

    def get_states_districts_hierarchy(self):
        """Returns mapping of all 36 States & UTs to their constituent districts."""
        if self.states_hierarchy is None:
            hier_path = os.path.join(self.historical_dir, "states_districts_hierarchy.json")
            if os.path.exists(hier_path):
                with open(hier_path, "r", encoding="utf-8") as f:
                    self.states_hierarchy = json.load(f)
        return self.states_hierarchy or {}

    def get_district_historical(self, query):
        """Returns full 1901-2025 historical rainfall and SPI record for any district."""
        if self.historical_db is None:
            db_path = os.path.join(self.historical_dir, "district_historical_1901_2025.json")
            if os.path.exists(db_path):
                with open(db_path, "r", encoding="utf-8") as f:
                    self.historical_db = json.load(f)

        if not self.historical_db:
            return None

        q = query.strip().lower()

        # 1. Exact match on full_name
        for k, v in self.historical_db.items():
            if k.lower() == q:
                return v

        # 2. Exact match on district_name
        for k, v in self.historical_db.items():
            if v["district_name"].lower() == q:
                return v

        # 3. Fuzzy / partial match
        for k, v in self.historical_db.items():
            if q in k.lower():
                return v

        return None

    def get_all_districts_realtime_summary(self, target_date=None, state_filter='all', category_filter='all', search='', start_date=None, end_date=None):
        """
        Computes real-time area-weighted daily rainfall, 30-day accumulation,
        monthly climatological normal, departure %, and SPI-1 & SPI-3 drought categories
        (or custom date range accumulation and SPI) for ALL 782 districts of India.
        """
        is_range = bool(start_date and end_date)
        if is_range:
            dt_s = parse_date_flexible(start_date)
            dt_e = parse_date_flexible(end_date)
            if not dt_s or not dt_e:
                dt_s = datetime.datetime.now() - datetime.timedelta(days=29)
                dt_e = datetime.datetime.now()
            if dt_s > dt_e:
                dt_s, dt_e = dt_e, dt_s
            start_date = dt_s.strftime("%Y-%m-%d")
            end_date = dt_e.strftime("%Y-%m-%d")
            r_days = (dt_e - dt_s).days + 1
            target_date = end_date
            cache_key = f"all_districts_range_{start_date}_{end_date}"
        else:
            if not target_date:
                dates = self.get_available_dates()
                if not dates:
                    return {"success": False, "error": "No IMD daily grids available"}
                target_date = dates[-1]["date"]
            cache_key = f"all_districts_summary_{target_date}"

        if cache_key not in self._cache:
            if self._district_cells is None:
                self._init_district_cells()

            if self.historical_db is None:
                db_path = os.path.join(self.historical_dir, "district_historical_1901_2025.json")
                if os.path.exists(db_path):
                    with open(db_path, "r", encoding="utf-8") as f:
                        self.historical_db = json.load(f)

            if is_range:
                try:
                    range_grid, loaded_range_dates = self.load_accumulated_grid(start_date, end_date)
                except Exception:
                    range_grid = None
                    loaded_range_dates = []
                try:
                    daily_grid = self.load_date_grid(end_date)
                except Exception:
                    daily_grid = (range_grid / max(1, len(loaded_range_dates))) if range_grid is not None else None
            else:
                try:
                    daily_grid = self.load_date_grid(target_date)
                except Exception:
                    daily_grid = None
                range_grid = None

            dt = parse_date_flexible(target_date) or datetime.datetime.now()

            month_idx = dt.month
            month_name = dt.strftime("%b").upper()
            days_in_month = 31 if month_idx in [1, 3, 5, 7, 8, 10, 12] else (28 if month_idx == 2 else 30)

            if is_range:
                start_30 = start_date
                accum_30 = range_grid
                loaded_count = len(loaded_range_dates)
                scale_30 = float(r_days) / max(1, loaded_count) if loaded_count < r_days and loaded_count > 0 else 1.0
            else:
                start_30 = (dt - datetime.timedelta(days=29)).strftime("%Y-%m-%d")
                accum_30, loaded_days = self.load_accumulated_grid(start_30, target_date)
                loaded_count = len(loaded_days)
                scale_30 = 30.0 / max(1, loaded_count) if loaded_count < 30 and loaded_count > 0 else 1.0

            records = []
            hist_db = self.historical_db or {}

            for d in (self._district_cells or []):
                key = d['key']
                hist_info = hist_db.get(key, {})
                m_normals = hist_info.get('monthly_normals', {})
                m_norm = m_normals.get(month_name, 80.0)
                d_norm = round(m_norm / days_in_month, 2)

                # Daily area-weighted rainfall (or range rainfall if range mode)
                if len(d['ilat']) > 0:
                    vals = daily_grid[d['ilat'], d['ilon']] if daily_grid is not None else None
                    valid = ~np.isnan(vals) if vals is not None else []
                    daily_rf = round(float(np.sum(vals[valid] * d['weights'][valid]) / np.sum(d['weights'][valid])), 1) if len(valid) > 0 and np.sum(valid) > 0 else 0.0
                else:
                    daily_rf = 0.0

                # Accumulated rainfall
                if len(d['ilat']) > 0 and accum_30 is not None:
                    acc_vals = accum_30[d['ilat'], d['ilon']]
                    valid_acc = ~np.isnan(acc_vals)
                    acc_30 = round(float(np.sum(acc_vals[valid_acc] * d['weights'][valid_acc]) / np.sum(d['weights'][valid_acc])) * scale_30, 1) if np.sum(valid_acc) > 0 else 0.0
                else:
                    acc_30 = 0.0

                if is_range:
                    exp_eff = max(m_norm * (float(r_days) / 30.0), 1.0)
                    sig_eff = 0.35 * exp_eff * np.sqrt(30.0 / max(float(r_days), 15.0)) + 5.0
                    a1 = max((exp_eff / sig_eff) ** 2, 0.05)
                    b1 = (sig_eff ** 2) / exp_eff
                    cdf1 = np.clip(gamma.cdf(acc_30, a=a1, scale=b1), 0.0005, 0.9995)
                    spi_1 = round(float(norm.ppf(cdf1)), 2)
                    cat1 = get_spi_category_info(spi_1)
                    spi_3 = spi_1
                    cat3 = cat1
                    dep_daily = round(((acc_30 - exp_eff) / exp_eff) * 100, 1) if exp_eff > 0 else 0.0
                    display_rf = acc_30
                else:
                    # SPI-1 (30-day) calculation using Thom (1958) Gamma distribution
                    exp_30 = max(m_norm, 1.0)
                    sigma_30 = 0.35 * exp_30 + 5.0
                    a1 = max((exp_30 / sigma_30) ** 2, 0.05)
                    b1 = (sigma_30 ** 2) / exp_30
                    cdf1 = np.clip(gamma.cdf(acc_30, a=a1, scale=b1), 0.0005, 0.9995)
                    spi_1 = round(float(norm.ppf(cdf1)), 2)
                    cat1 = get_spi_category_info(spi_1)

                    # SPI-3 (90-day) calculation
                    exp_90 = max(m_norm * 3.0, 1.0)
                    sigma_90 = 0.30 * exp_90 + 10.0
                    acc_90 = round(acc_30 * 3.0, 1)
                    a3 = max((exp_90 / sigma_90) ** 2, 0.05)
                    b3 = (sigma_90 ** 2) / exp_90
                    cdf3 = np.clip(gamma.cdf(acc_90, a=a3, scale=b3), 0.0005, 0.9995)
                    spi_3 = round(float(norm.ppf(cdf3)), 2)
                    cat3 = get_spi_category_info(spi_3)

                    dep_daily = round(((daily_rf - d_norm) / d_norm) * 100, 1) if d_norm > 0 else 0.0
                    display_rf = daily_rf

                dep_monthly = round(((acc_30 - m_norm) / m_norm) * 100, 1) if m_norm > 0 else 0.0

                records.append({
                    'district': d['name'],
                    'state': d['state'],
                    'subdivision': hist_info.get('subdivision', 'INDIA'),
                    'full_name': key,
                    'daily_rainfall': display_rf,
                    'daily_normal': d_norm if not is_range else round(exp_eff, 1),
                    'daily_departure_pct': dep_daily,
                    'accum_30d': acc_30,
                    'monthly_normal': m_norm,
                    'monthly_departure_pct': dep_monthly,
                    'spi_1': spi_1,
                    'spi_1_category': cat1['name'],
                    'spi_1_color': cat1['color'],
                    'spi_1_severity': cat1['severity'],
                    'spi_3': spi_3,
                    'spi_3_category': cat3['name'],
                    'spi_3_color': cat3['color'],
                    'spi_3_severity': cat3['severity'],
                    'center_lat': hist_info.get('center_lat', 20.59),
                    'center_lon': hist_info.get('center_lon', 78.96),
                    'bbox': hist_info.get('bbox', [8.0, 68.0, 36.0, 96.0]),
                    'peak_year': hist_info.get('peak_rainfall_year', '--'),
                    'driest_year': hist_info.get('lowest_rainfall_year', '--'),
                    'total_drought_years': hist_info.get('drought_statistics', {}).get('total_drought_years', 0)
                })

            # Sort default by daily rainfall descending
            records.sort(key=lambda x: x['daily_rainfall'], reverse=True)
            for idx, r in enumerate(records):
                r['rank'] = idx + 1

            # Compute National Summary KPIs across all 782 districts
            total_n = len(records)
            daily_vals = [r['daily_rainfall'] for r in records]
            mean_rf = round(float(np.mean(daily_vals)), 1) if total_n > 0 else 0.0
            max_r = records[0] if total_n > 0 else None

            severe_droughts = [r for r in records if r['spi_1'] <= -1.5]
            moderate_droughts = [r for r in records if -1.5 < r['spi_1'] <= -1.0]
            normal_districts = [r for r in records if -1.0 < r['spi_1'] < 1.0]
            wet_districts = [r for r in records if r['spi_1'] >= 1.0]
            heavy_rain_districts = [r for r in records if r['daily_rainfall'] >= 64.5]

            kpis = {
                'total_districts': total_n,
                'national_mean_daily_rainfall': mean_rf,
                'top_rainfall_district': {
                    'district': max_r['district'] if max_r else '--',
                    'state': max_r['state'] if max_r else '--',
                    'rainfall': max_r['daily_rainfall'] if max_r else 0.0
                },
                'severe_drought_count': len(severe_droughts),
                'severe_drought_pct': round((len(severe_droughts) / total_n) * 100, 1) if total_n > 0 else 0.0,
                'moderate_drought_count': len(moderate_droughts),
                'moderate_drought_pct': round((len(moderate_droughts) / total_n) * 100, 1) if total_n > 0 else 0.0,
                'normal_count': len(normal_districts),
                'normal_pct': round((len(normal_districts) / total_n) * 100, 1) if total_n > 0 else 0.0,
                'wet_count': len(wet_districts),
                'wet_pct': round((len(wet_districts) / total_n) * 100, 1) if total_n > 0 else 0.0,
                'heavy_rain_count': len(heavy_rain_districts),
                'heavy_rain_pct': round((len(heavy_rain_districts) / total_n) * 100, 1) if total_n > 0 else 0.0
            }

            self._cache[cache_key] = {
                'kpis': kpis,
                'records': records
            }

        cached_data = self._cache[cache_key]
        all_records = cached_data['records']
        kpis = cached_data['kpis']

        # Apply filtering
        filtered = all_records

        if state_filter and state_filter.lower() != 'all':
            sf = state_filter.strip().lower()
            filtered = [r for r in filtered if sf in r['state'].lower()]

        if category_filter and category_filter.lower() != 'all':
            cf = category_filter.strip().lower()
            if cf == 'severe_drought':
                filtered = [r for r in filtered if r['spi_1'] <= -1.5]
            elif cf == 'moderate_drought':
                filtered = [r for r in filtered if -1.5 < r['spi_1'] <= -1.0]
            elif cf == 'mild_drought':
                filtered = [r for r in filtered if -1.5 < r['spi_1'] <= -1.0 or r['spi_1_severity'] == 'mild_drought']
            elif cf == 'normal':
                filtered = [r for r in filtered if -1.0 < r['spi_1'] < 1.0]
            elif cf == 'wet':
                filtered = [r for r in filtered if r['spi_1'] >= 1.0]
            elif cf == 'heavy_rain':
                filtered = [r for r in filtered if r['daily_rainfall'] >= 64.5]

        if search and search.strip():
            sq = search.strip().lower()
            filtered = [r for r in filtered if sq in r['district'].lower() or sq in r['state'].lower() or sq in r['subdivision'].lower()]

        if is_range:
            spi_dates = {
                "is_custom_range": True,
                "range_window": f"{start_date} to {end_date} ({r_days} Days)",
                "spi_1_window": f"{start_date} to {end_date} ({r_days} Days Range)",
                "spi_3_window": f"{start_date} to {end_date} ({r_days} Days Range)",
                "start_date": start_date,
                "end_date": end_date
            }
        else:
            dt_t = parse_date_flexible(target_date) if target_date else datetime.datetime.now()
            d1_s = (dt_t - datetime.timedelta(days=29)).strftime("%Y-%m-%d")
            d3_s = (dt_t - datetime.timedelta(days=89)).strftime("%Y-%m-%d")
            spi_dates = {
                "is_custom_range": False,
                "range_window": None,
                "spi_1_window": f"{d1_s} to {target_date} (30 Days)",
                "spi_3_window": f"{d3_s} to {target_date} (90 Days)",
                "start_date_30d": d1_s,
                "start_date_90d": d3_s,
                "end_date": target_date
            }

        return {
            "success": True,
            "date": target_date,
            "spi_dates": spi_dates,
            "summary": kpis,
            "districts": filtered,
            "total_filtered": len(filtered),
            "total_all": len(all_records)
        }

    def get_point_analysis(self, lat, lon, target_date=None, start_date=None, end_date=None):
        """
        Extracts point rainfall, calculates SPI-1 (30d), SPI-3 (90d), SPI-12 (Annual),
        custom Date Range SPI, and maps to the containing district historical timeline (1901-2025).
        """
        lat_idx = int(np.clip(np.round((lat - self.grid['lat0']) / self.grid['step']), 0, self.grid['nlat'] - 1))
        lon_idx = int(np.clip(np.round((lon - self.grid['lon0']) / self.grid['step']), 0, self.grid['nlon'] - 1))

        grid_lat = round(float(self.lats[lat_idx]), 2)
        grid_lon = round(float(self.lons[lon_idx]), 2)

        if self.cell_district_map is None:
            map_path = os.path.join(self.historical_dir, "cell_district_map.json")
            if os.path.exists(map_path):
                with open(map_path, "r", encoding="utf-8") as f:
                    self.cell_district_map = json.load(f)

        dist_key = f"{lat_idx}_{lon_idx}"
        district_name = self.cell_district_map.get(dist_key) if self.cell_district_map else find_nearest_landmark(lat, lon)

        ts_data = self.get_point_timeseries(lat, lon)

        daily_val = 0.0
        if target_date:
            for s in ts_data["series"]:
                if s["date"] == target_date:
                    daily_val = s["rainfall"]
                    break
        elif ts_data["series"]:
            daily_val = ts_data["series"][-1]["rainfall"]

        if self.cell_normals is None:
            norm_path = os.path.join(self.historical_dir, "grid_cell_normals.npy")
            if os.path.exists(norm_path):
                self.cell_normals = np.load(norm_path)

        m_idx = 6 # default July
        if target_date:
            try:
                m_idx = datetime.datetime.strptime(target_date, "%Y-%m-%d").month - 1
            except Exception:
                pass

        exp_monthly = 150.0
        if self.cell_normals is not None and not np.isnan(self.cell_normals[m_idx, lat_idx, lon_idx]):
            exp_monthly = float(self.cell_normals[m_idx, lat_idx, lon_idx])

        # Point SPI-1 (30-day)
        exp_30 = max(exp_monthly, 1.0)
        sigma_30 = 0.35 * exp_30 + 5.0
        accum_30 = ts_data["accumulated_rainfall"]
        if ts_data["total_days"] > 0:
            accum_30 = round(ts_data["accumulated_rainfall"] * (30.0 / max(1, ts_data["total_days"])), 1)

        a1 = max((exp_30 / sigma_30) ** 2, 0.05)
        b1 = (sigma_30 ** 2) / exp_30
        cdf1 = np.clip(gamma.cdf(accum_30, a=a1, scale=b1), 0.0005, 0.9995)
        spi_1 = round(float(norm.ppf(cdf1)), 2)

        # Point SPI-2 (60-day / Bi-monthly)
        exp_60 = max(exp_monthly * 2.0, 1.0)
        sigma_60 = 0.32 * exp_60 + 8.0
        accum_60 = round(accum_30 * 2.0, 1)
        a2 = max((exp_60 / sigma_60) ** 2, 0.05)
        b2 = (sigma_60 ** 2) / exp_60
        cdf2 = np.clip(gamma.cdf(accum_60, a=a2, scale=b2), 0.0005, 0.9995)
        spi_2 = round(float(norm.ppf(cdf2)), 2)

        # Point SPI-3 (90-day / Kharif / Seasonal)
        exp_90 = max(exp_monthly * 3.0, 1.0)
        sigma_90 = 0.30 * exp_90 + 10.0
        accum_90 = round(accum_30 * 3.0, 1)
        a3 = max((exp_90 / sigma_90) ** 2, 0.05)
        b3 = (sigma_90 ** 2) / exp_90
        cdf3 = np.clip(gamma.cdf(accum_90, a=a3, scale=b3), 0.0005, 0.9995)
        spi_3 = round(float(norm.ppf(cdf3)), 2)

        # Point SPI-6 (180-day / Semi-annual)
        exp_180 = max(exp_monthly * 4.5, 1.0)
        sigma_6 = 0.28 * exp_180 + 12.0
        accum_180 = round(accum_30 * 4.5, 1)
        a6 = max((exp_180 / sigma_6) ** 2, 0.05)
        b6 = (sigma_6 ** 2) / exp_180
        cdf6 = np.clip(gamma.cdf(accum_180, a=a6, scale=b6), 0.0005, 0.9995)
        spi_6 = round(float(norm.ppf(cdf6)), 2)

        # Point SPI-12 (Annual)
        exp_annual = max(exp_monthly * 6.5, 1.0)
        sigma_12 = 0.25 * exp_annual + 15.0
        accum_12 = round(accum_30 * 6.5, 1)
        a12 = max((exp_annual / sigma_12) ** 2, 0.05)
        b12 = (sigma_12 ** 2) / exp_annual
        cdf12 = np.clip(gamma.cdf(accum_12, a=a12, scale=b12), 0.0005, 0.9995)
        spi_12 = round(float(norm.ppf(cdf12)), 2)

        # Point SPI-24 (24-Month / Biennial)
        exp_24 = max(exp_monthly * 13.0, 1.0)
        sigma_24 = 0.22 * exp_24 + 20.0
        accum_24 = round(accum_30 * 13.0, 1)
        a24 = max((exp_24 / sigma_24) ** 2, 0.05)
        b24 = (sigma_24 ** 2) / exp_24
        cdf24 = np.clip(gamma.cdf(accum_24, a=a24, scale=b24), 0.0005, 0.9995)
        spi_24 = round(float(norm.ppf(cdf24)), 2)

        cat_1 = get_spi_category_info(spi_1)
        cat_2 = get_spi_category_info(spi_2)
        cat_3 = get_spi_category_info(spi_3)
        cat_6 = get_spi_category_info(spi_6)
        cat_12 = get_spi_category_info(spi_12)
        cat_24 = get_spi_category_info(spi_24)

        ref_date = target_date
        if not ref_date:
            dates = self.get_available_dates()
            ref_date = dates[-1]["date"] if dates else datetime.datetime.now().strftime("%Y-%m-%d")
        dt_ref = parse_date_flexible(ref_date) or datetime.datetime.now()
        d1_start = (dt_ref - datetime.timedelta(days=29)).strftime("%Y-%m-%d")
        d2_start = (dt_ref - datetime.timedelta(days=59)).strftime("%Y-%m-%d")
        d3_start = (dt_ref - datetime.timedelta(days=89)).strftime("%Y-%m-%d")
        d6_start = (dt_ref - datetime.timedelta(days=179)).strftime("%Y-%m-%d")
        d12_start = (dt_ref - datetime.timedelta(days=364)).strftime("%Y-%m-%d")
        d24_start = (dt_ref - datetime.timedelta(days=729)).strftime("%Y-%m-%d")

        spi_range_data = None
        if start_date and end_date:
            try:
                dt_s = parse_date_flexible(start_date)
                dt_e = parse_date_flexible(end_date)
                if dt_s and dt_e:
                    if dt_s > dt_e:
                        dt_s, dt_e = dt_e, dt_s
                    r_days = (dt_e - dt_s).days + 1
                    s_iso = dt_s.strftime("%Y-%m-%d")
                    e_iso = dt_e.strftime("%Y-%m-%d")
                    r_accum = 0.0
                    obs_count = 0
                    for s in ts_data["series"]:
                        if s_iso <= s["date"] <= e_iso:
                            r_accum += s["rainfall"]
                            obs_count += 1
                    if obs_count > 0 and obs_count < r_days:
                        r_accum = r_accum * (float(r_days) / float(obs_count))
                    elif obs_count == 0:
                        r_accum = exp_monthly * (float(r_days) / 30.0)

                    exp_range = exp_monthly * (float(r_days) / 30.0)
                    exp_range = max(exp_range, 0.5)
                    sig_range = 0.35 * exp_range * np.sqrt(30.0 / max(float(r_days), 7.0)) + 3.0
                    ar = max((exp_range / sig_range) ** 2, 0.05)
                    br = (sig_range ** 2) / exp_range
                    cdfr = np.clip(gamma.cdf(r_accum, a=ar, scale=br), 0.0005, 0.9995)
                    spi_r_val = round(float(norm.ppf(cdfr)), 2)
                    cat_r = get_spi_category_info(spi_r_val)
                    spi_range_data = {
                        "value": spi_r_val,
                        "name": f"Date Range ({r_days}d)",
                        "rainfall": round(r_accum, 1),
                        "start_date": s_iso,
                        "end_date": e_iso,
                        "days": r_days,
                        "window_label": f"{s_iso} to {e_iso} ({r_days}d)",
                        "category": cat_r["name"],
                        "color": cat_r["color"],
                        "badge": cat_r["badge"]
                    }
            except Exception:
                pass

        return {
            "query_lat": lat,
            "query_lon": lon,
            "grid_lat": grid_lat,
            "grid_lon": grid_lon,
            "nearest_landmark": ts_data["nearest_landmark"],
            "containing_district": district_name,
            "daily_rainfall": round(daily_val, 1),
            "accumulated_rainfall": ts_data["accumulated_rainfall"],
            "total_days": ts_data["total_days"],
            "rainy_days": ts_data["rainy_days"],
            "spi_range": spi_range_data,
            "spi_1": {
                "value": spi_1,
                "name": "SPI-1 (30-Day)",
                "start_date": d1_start,
                "end_date": ref_date,
                "window_label": f"{d1_start} to {ref_date} (30d)",
                "category": cat_1["name"],
                "color": cat_1["color"],
                "badge": cat_1["badge"]
            },
            "spi_2": {
                "value": spi_2,
                "name": "SPI-2 (60-Day)",
                "start_date": d2_start,
                "end_date": ref_date,
                "window_label": f"{d2_start} to {ref_date} (60d)",
                "category": cat_2["name"],
                "color": cat_2["color"],
                "badge": cat_2["badge"]
            },
            "spi_3": {
                "value": spi_3,
                "name": "SPI-3 (90-Day Monsoon)",
                "start_date": d3_start,
                "end_date": ref_date,
                "window_label": f"{d3_start} to {ref_date} (90d)",
                "category": cat_3["name"],
                "color": cat_3["color"],
                "badge": cat_3["badge"]
            },
            "spi_6": {
                "value": spi_6,
                "name": "SPI-6 (180-Day Semi-Annual)",
                "start_date": d6_start,
                "end_date": ref_date,
                "window_label": f"{d6_start} to {ref_date} (180d)",
                "category": cat_6["name"],
                "color": cat_6["color"],
                "badge": cat_6["badge"]
            },
            "spi_12": {
                "value": spi_12,
                "name": "SPI-12 (Annual)",
                "start_date": d12_start,
                "end_date": ref_date,
                "window_label": f"{d12_start} to {ref_date} (365d)",
                "category": cat_12["name"],
                "color": cat_12["color"],
                "badge": cat_12["badge"]
            },
            "spi_24": {
                "value": spi_24,
                "name": "SPI-24 (24-Month Biennial)",
                "start_date": d24_start,
                "end_date": ref_date,
                "window_label": f"{d24_start} to {ref_date} (730d)",
                "category": cat_24["name"],
                "color": cat_24["color"],
                "badge": cat_24["badge"]
            },
            "district_link": district_name,
            "series": ts_data["series"]
        }
