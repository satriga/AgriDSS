# AgriDSS: IMD Gridded Rainfall Decision Support System

An interactive, high-performance GIS web application for visualizing, analyzing, and animating **India Meteorological Department (IMD) daily gridded rainfall data** (0.25° &times; 0.25° resolution).

Developed for meteorological research, hydrological assessment, and Agricultural Decision Support (AgriDSS).

---

## 🌟 Key Features

### 🌧️ 1. IMD Gridded Rainfall GIS Visualizer (`/`)
- **Native 0.25° Grid Display**: Hardware-accelerated HTML5 Canvas overlay rendering 17,415 grid cells at 60 fps.
- **Dual Rendering Modes**: Switch between **Smooth Bilinear Heatmap** and **Discrete 0.25° Grid Cells**.
- **Official IMD Rainfall Intensity Classification**: 7 standard intensity tiers with official meteorological color scaling.
- **Dynamic Timeline & Playback Animation**: Step through daily observations, adjust playback speed, scrub timeline.
- **Point-Level Probe & Historical Time-Series**: Click anywhere on India to inspect coordinates, nearest landmark, and time-series trends.
- **Agricultural Decision Support (AgriDSS)**: Automated inundation warnings, Kharif sowing suitability, and chemical spraying windows.
- **Live IMD Data Fetcher & Uploader**: Direct download from IMD Pune archives (`imdlib`) or custom `.grd` binary upload.

---

### 🛡️ 2. PMFBY Crop Insurance Analytics Dashboard (`/pmfby`)
Based on official data from the [Pradhan Mantri Fasal Bima Yojana Portal](https://www.pmfby.gov.in/adminStatistics/dashboard):
- **Executive Metrics & KPIs**: Total Applications (36+ Cr), Area Insured (Lakh Ha), Sum Insured (₹ Lakh Cr), Gross Premium, Claims Settled (₹ Cr), Benefited Farmers, and Loss Ratio.
- **Season & Year Filtering**: Filter across all 18 historical and recent seasons (**Kharif & Rabi from 2018 to 2026**).
- **District-Level Explorer with Insurance Company Mapping**:
  - Year filter for districts (2024, 2023, 2022).
  - State filter dropdown.
  - **Designated Insurance Company filter** mapped directly from the official **PMFBY Insurance Premium Calculator** hierarchy API (`/landingPage/districtState`).
  - Search districts, states, or insurers in real-time.
  - Interactive ranking charts toggleable between **States**, **Districts**, and **Insurance Companies**.
- **Interactive Visualizations (Chart.js)**:
  1. *Enrollment & Area Insured Growth*: Year-on-year dual-axis bar & line trend.
  2. *Premium Subsidy Sharing*: Stacked bar chart showing Farmer Share vs. State Subsidy vs. Central Govt Subsidy.
  3. *Claims Paid vs. Gross Premium Comparison*: Financial loss ratio and payout efficiency.
  4. *5-Stage Crop Claim Distribution*: End-of-season yield losses, mid-season adversity, localised calamities, post-harvest losses, and prevented sowing.
  5. *Demographics & Inclusivity*: Marginal/Small farmer coverage (83%+), OBC/SC/ST/General, and gender ratios.
  6. *3-Way Ranking Chart*: Toggle between **State Rankings**, **Top 10 Districts**, and **Insurance Company Performance**.
- **Multi-Sheet Excel Workbook Export (`.xlsx`)**:
  - Direct download button generating a styled Excel file with 6 comprehensive sheets:
    - `National_Summary_2018_2026`: Complete chronological time-series.
    - `State_Wise_Performance`: Detailed state metrics.
    - `District_Wise_Performance`: District-level breakdown with designated Insurance Company.
    - `Insurance_Company_Summary`: Insurance company metrics aggregated year-wise.
    - `Claims_5_Stages_Breakdown`: 5 claim stages breakdown.
    - `Farmer_Demographics_Inclusivity`: Social and landholding inclusivity.
- **CSV Data Export**: Instant tabular CSV download filtered by selected year, state, and insurance company.

### 🏢 3. Insurance Company Analytics & Daily Sync (`/pmfby/companies`)
A dedicated dynamic analytics page focused on official PMFBY & RWBCIS Insurance Company allocations and operations:
- **Comprehensive Multi-Year Coverage**: All years (**2018 to 2026**) split by **Season** (*Kharif* & *Rabi*) and **Scheme** (*PMFBY* Yield-based & *RWBCIS* Weather-based).
- **Flexible Provision to Select View Level**:
  - `🏢 Insurance Company Summary`: Insurer portfolio leaderboard, rankings, and aggregated market share.
  - `🗺️ State-wise View`: State-level performance breakdown by Insurance Company.
  - `📍 District-wise View`: District-level granularity with assigned Insurance Companies.
- **Multi-Filter Controls**:
  - Filter by specific Insurance Company (all 21 notified general insurers).
  - Filter by Year (2018–2026), Season (Kharif, Rabi), Scheme (PMFBY, RWBCIS), and State.
  - Instant typing search across Company, State, or District.
- **Dynamic Daily Auto-Sync Engine**:
  - Automated background worker checks `pmfby.gov.in` every 24 hours.
  - Header badge displaying live sync status: `🟢 Daily Sync Active • Last Checked: <Timestamp> • Up to date`.
  - **"🔄 Check for Updates Now"** button: Triggers real-time check against PMFBY APIs and refreshes local caches.
- **Interactive Visualizations (Chart.js)**:
  1. *Market Share by Farmers Enrolled*: Insurer portfolio breakdown.
  2. *Gross Premium vs Claims Settled*: Dual-bar comparison in ₹ Crore.
  3. *Financial Loss Ratio (%)*: Risk benchmark with color bands.
  4. *Season & Scheme Split*: PMFBY vs RWBCIS farmer distribution.
- **Custom Multi-Sheet Excel Exporter (`.xlsx`)**:
  - `Company_Summary`: Ranked portfolio leaderboard.
  - `State_Wise_Distribution`: State breakdown by insurer.
  - `District_Wise_Allocation`: District breakdown by insurer.
- **CSV Data Exporter**: Instant download of the currently filtered view.

---

### 📊 4. PMFBY Actuarial Pricing, Threshold Yield & Tender Review (`/pmfby/pricing`)
A full-stack actuarial pricing intelligence module designed for tender underwriting, bidding analysis, and historical yield review:
- **3 Threshold Yield (TY) Methodologies**:
  - `3B5`: Mean of the best 3 historical yields out of the preceding 5 years &times; Indemnity Level.
  - `5B7`: Standard PMFBY operational guideline (mean of best 5 out of 7 years &times; Indemnity Level).
  - `TM` (Trimmed Mean): Preceding 10 years minus the 2 worst calamity years &times; Indemnity Level.
- **Dynamic Indemnity Recalculation Engine**:
  - Live recalculation across 70%, 80%, 90% or custom percentage inputs.
  - Granular year-by-year shortfall % and payout calculations.
  - Dynamic update of Row-level, Crop-wise, Cluster-wise, and Portfolio-level **Burning Cost (BC %)**.
- **Cluster Underwriting Matrix & Bidding Simulation**:
  - Provision to specify **CAT Loading / Discounting (%)** and **Other Loading / Discounting (%)** at the cluster level (percentage of BC or additive percentage points).
  - Calculation of **Actuarial Pure Premium Rate (APPR %)**.
  - User-configurable **Quoted Premium Rate (%)** per cluster with automatic **Projected Loss Ratio (PLR %)** evaluation ($\frac{\text{APPR}}{\text{Quoted Premium}} \times 100\%$).
- **Multi-Workbook Tender Analysis**:
  - Bulk upload multiple state tender sheets or CCE notification files simultaneously.
  - Automatic State selection dropdown with state-isolated analysis and consolidated portfolio view.
- **Actuarial Saved Analyses Vault**:
  - Save, inspect, reload, and delete customized bidding simulations and pricing audits.
  - Persisted locally under `data/saved_analyses/` for future reference.
- **Beed Model (80:110) & Cup-and-Cap Simulations**:
  - Interactive risk-sharing bands modeling state clawbacks vs insurer retained margins.

---

## 🚀 Getting Started

### 1. Requirements
- Python 3.10+
- Dependencies: `flask`, `numpy`, `imdlib`, `pandas`, `matplotlib`, `xarray`, `cryptography`, `openpyxl`, `requests`

### 2. Run the Application
```powershell
py -3 app.py
```
Or run `.\run.ps1`

### 3. Open in Browser
- **IMD Gridded Rainfall GIS Visualizer**: [http://localhost:5000](http://localhost:5000)
- **PMFBY Crop Insurance Analytics**: [http://localhost:5000/pmfby](http://localhost:5000/pmfby)
- **Insurance Company Analytics & Daily Sync**: [http://localhost:5000/pmfby/companies](http://localhost:5000/pmfby/companies)
- **PMFBY Actuarial Pricing & Tender Review**: [http://localhost:5000/pmfby/pricing](http://localhost:5000/pmfby/pricing)

---

## 📁 Project Architecture

```
d:\AGRIDSS\
├── app.py                     # Flask Web Server & Integrated REST API endpoints
├── imd_processor.py           # IMD binary parser, statistics & AgriDSS engine
├── pmfby_processor.py         # PMFBY decryption, caching, district IC mapping & Excel exporter
├── excel_review_service.py    # Actuarial pricing, TY calculation (3B5, 5B7, TM), BC % & PLR %
├── pmfby_pricing_engine.py    # Actuarial rates, Beed 80:110 & Cup-and-Cap simulation engine
├── saved_analysis_service.py  # Actuarial analyses persistence vault
├── PMFBY_Pricing_Review_2018_2026.xlsx # Executive actuarial pricing review workbook
├── build_ic_mapping.py        # PMFBY Premium Calculator hierarchy scraper
├── run.ps1                    # Quick launcher script
├── data/
│   ├── grd/                   # Cached IMD 0.25° daily rainfall binary files
│   ├── india_states.geojson   # India state boundary polygons
│   ├── pmfby/                 # Decrypted PMFBY caches & ic_district_mapping.json
│   └── saved_analyses/        # Persisted actuarial pricing review vault
├── static/
│   ├── css/
│   │   ├── style.css          # IMD GIS dashboard stylesheet
│   │   └── pmfby.css          # PMFBY crop insurance analytics stylesheet
│   ├── js/
│   │   ├── map.js             # Leaflet canvas raster layer & interaction
│   │   ├── charts.js          # IMD time-series & category distribution charts
│   │   ├── app.js             # IMD state management & playback animation
│   │   └── pmfby.js           # PMFBY charts, district filters & IC explorer
│   └── vendor/                # Local Leaflet & Chart.js libraries
└── templates/
    ├── index.html             # IMD GIS visualizer template
    ├── login.html             # Security & authentication gateway
    ├── pmfby.html             # PMFBY administrative analytics template
    ├── pmfby_companies.html   # Insurance company analytics template
    └── pmfby_pricing.html     # Actuarial pricing, TY (3B5/5B7/TM) & tender audit template
    └── pmfby.html             # PMFBY analytics dashboard template
```

---

## 📡 REST API Documentation

| Endpoint | Method | Description |
|---|---|---|
| `GET /api/dates` | GET | List all available cached IMD observation dates |
| `GET /api/grid?date=YYYY-MM-DD` | GET | Retrieve gridded rainfall matrix, stats & categories |
| `GET /api/grid?mode=accumulate&accum_days=7` | GET | Multi-day cumulative rainfall grid & analytics |
| `GET /api/point?lat=18.97&lon=72.82` | GET | Point time-series across all available dates |
| `POST /api/fetch` | POST | Fetch official IMD `.grd` from IMD Pune archives |
| `POST /api/upload` | POST | Upload a custom `.grd` or `.bin` grid file |
| `GET /api/export/csv` | GET | Download grid data as CSV |
| `GET /api/export/geojson` | GET | Download rainfall grid polygons as GeoJSON |
| `GET /api/india_states` | GET | India state boundaries GeoJSON layer |
| `GET /api/pmfby/summary` | GET | Complete PMFBY national season-wise summary (2018–2026) |
| `GET /api/pmfby/state_report?year=2024&season=01` | GET | State-wise performance report |
| `GET /api/pmfby/district_report?year=2024&season=01&company=Bajaj` | GET | District-level report with mapped Insurance Companies & filters |
| `GET /api/pmfby/companies` | GET | List of all notified PMFBY Insurance Companies |
| `GET /api/pmfby/company_analytics` | GET | Multi-dimensional Insurance Company analytics (by year, season, scheme, level, company, state) |
| `GET /api/pmfby/sync_status` | GET | Status of automated daily PMFBY background sync |
| `POST /api/pmfby/sync_refresh` | POST | Trigger on-demand check against PMFBY government portal |
| `GET /api/pmfby/export/company_excel` | GET | Download custom 3-sheet Insurance Company Excel workbook |
| `GET /api/pmfby/export/company_csv` | GET | Download filtered Insurance Company CSV |
| `GET /api/pmfby/export/excel` | GET | Download 6-sheet formatted National Excel (`.xlsx`) workbook |
| `GET /api/pmfby/export/districts_csv?year=2024&company=Bajaj` | GET | Download filtered district CSV |
