"""
IMD Gridded Rainfall & PMFBY Crop Insurance Web Application & API
Provides interactive GIS visualizer, meteorological analysis,
dynamic timeline playback, point probing, and official PMFBY analytics.
"""

import os
import io
import csv
import json
import datetime
import numpy as np
from flask import Flask, render_template, request, jsonify, send_file, Response, session, redirect, url_for
from werkzeug.utils import secure_filename
from imd_processor import IMDProcessor, IMD_CATEGORIES, SPI_CATEGORIES
from pmfby_processor import PMFBYProcessor
import live_weather
from excel_review_service import ExcelReviewService
from saved_analysis_service import SavedAnalysisService
from pmfby_pricing_engine import PMFBYPricingEngine

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'agridss-secret-key-gbgohain26-2026')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB max upload
processor = IMDProcessor(data_dir="data/grd")
pmfby_proc = PMFBYProcessor(cache_dir="data/pmfby")
pricing_engine = PMFBYPricingEngine(data_dir="data/pmfby")
PRICING_EXCEL_PATH = os.path.join(os.path.dirname(__file__), "PMFBY_Pricing_Review_2018_2026.xlsx")

# ============================================================================
# Security & Authentication Configuration
# ============================================================================
VALID_USERID = 'gbgohain26'
VALID_PASSWORDS = [':AgriDss@2609', 'AgriDss@2609']

@app.before_request
def require_login():
    """Restricts access across the entire AgriDSS application to authenticated users."""
    # Whitelist login, logout, static files, and favicon
    if request.endpoint in ['login', 'logout', 'static']:
        return
    if request.path.startswith('/static/') or request.path == '/favicon.ico':
        return
    
    # Check if user is authenticated in session
    if session.get('user') != VALID_USERID or not session.get('authenticated'):
        if request.path.startswith('/api/'):
            return jsonify({"success": False, "error": "Authentication required. Please login."}), 401
        return redirect(url_for('login', next=request.full_path if request.query_string else request.path))

# ============================================================================
# Authentication Pages
# ============================================================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Authentication gateway for AgriDSS."""
    if session.get('authenticated') and session.get('user') == VALID_USERID:
        return redirect(url_for('index'))
    
    error = None
    if request.method == 'POST':
        userid = request.form.get('userid', '').strip().lower()
        password = request.form.get('password', '').strip()
        
        if userid == VALID_USERID and password in VALID_PASSWORDS:
            session['authenticated'] = True
            session['user'] = VALID_USERID
            session['login_time'] = datetime.datetime.now().isoformat()
            next_url = request.args.get('next')
            if next_url and next_url.startswith('/') and not next_url.startswith('//'):
                return redirect(next_url)
            return redirect(url_for('index'))
        else:
            error = "Invalid User ID or Password. Access denied."
            
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    """Clears user session and logs out."""
    session.clear()
    return redirect(url_for('login'))

# ============================================================================
# Core Pages
# ============================================================================
@app.route('/')
def index():
    """Main IMD gridded rainfall dynamic web dashboard."""
    return render_template('index.html')

@app.route('/pmfby')
def pmfby_dashboard():
    """PMFBY Crop Insurance Administrative Statistics & Visualization Dashboard."""
    return render_template('pmfby.html')

# ============================================================================
# IMD Gridded Rainfall REST API
# ============================================================================
@app.route('/api/dates')
def api_dates():
    """Returns list of all available IMD daily rainfall dates."""
    dates = processor.get_available_dates()
    date_strings = [d["date"] for d in dates]
    return jsonify({
        "success": True,
        "count": len(dates),
        "dates": date_strings,
        "latest": date_strings[-1] if date_strings else None,
        "earliest": date_strings[0] if date_strings else None,
        "categories": IMD_CATEGORIES,
        "spi_categories": SPI_CATEGORIES
    })

@app.route('/api/imd/spi')
def api_imd_spi():
    """Returns spatial SPI grid & statistics for a given date, timescale, or custom date range."""
    date_str = request.args.get('date')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    # Normalize dates flexibly (supports YYYY-MM-DD, D/M/YYYY, etc.)
    if start_date:
        dt_s = processor.parse_date_flexible(start_date)
        if dt_s:
            start_date = dt_s.strftime("%Y-%m-%d")
    if end_date:
        dt_e = processor.parse_date_flexible(end_date)
        if dt_e:
            end_date = dt_e.strftime("%Y-%m-%d")
    if date_str:
        dt_d = processor.parse_date_flexible(date_str)
        if dt_d:
            date_str = dt_d.strftime("%Y-%m-%d")

    timescale_arg = request.args.get('timescale', default='3')
    if timescale_arg and timescale_arg.isdigit():
        timescale = int(timescale_arg)
    else:
        timescale = timescale_arg or 3

    if not date_str and not end_date:
        available = [d["date"] for d in processor.get_available_dates()]
        if not available:
            return jsonify({"success": False, "error": "No IMD gridded data available."}), 404
        date_str = available[-1]

    try:
        data = processor.compute_spatial_spi_grid(
            date_str=date_str or end_date,
            timescale=timescale,
            start_date=start_date,
            end_date=end_date
        )
        return jsonify(data)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route('/api/imd/districts')
def api_imd_districts():
    """Returns list of all 782 Indian districts with state names for search autocomplete."""
    dists = processor.get_district_list()
    return jsonify({
        "success": True,
        "count": len(dists),
        "districts": dists
    })

@app.route('/api/imd/states_hierarchy')
def api_imd_states_hierarchy():
    """Returns mapping of all 36 States & UTs to their constituent districts."""
    try:
        hier = processor.get_states_districts_hierarchy()
        return jsonify({
            "success": True,
            "count": len(hier),
            "states": hier
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/imd/district_summary')
def api_imd_district_summary():
    """
    Returns real-time area-weighted rainfall, departure, normals, and SPI drought summary
    for all 782 districts of India for target date or date range.
    """
    target_date = request.args.get('date')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if start_date:
        dt_s = processor.parse_date_flexible(start_date)
        if dt_s:
            start_date = dt_s.strftime("%Y-%m-%d")
    if end_date:
        dt_e = processor.parse_date_flexible(end_date)
        if dt_e:
            end_date = dt_e.strftime("%Y-%m-%d")
    if target_date:
        dt_t = processor.parse_date_flexible(target_date)
        if dt_t:
            target_date = dt_t.strftime("%Y-%m-%d")

    if start_date:
        dt_s = processor.parse_date_flexible(start_date)
        if dt_s:
            start_date = dt_s.strftime("%Y-%m-%d")
    if end_date:
        dt_e = processor.parse_date_flexible(end_date)
        if dt_e:
            end_date = dt_e.strftime("%Y-%m-%d")
    if target_date:
        dt_t = processor.parse_date_flexible(target_date)
        if dt_t:
            target_date = dt_t.strftime("%Y-%m-%d")

    state_filter = request.args.get('state', 'all')
    category_filter = request.args.get('category', 'all')
    search = request.args.get('search', '')

    try:
        res = processor.get_all_districts_realtime_summary(
            target_date=target_date,
            state_filter=state_filter,
            category_filter=category_filter,
            search=search,
            start_date=start_date,
            end_date=end_date
        )
        return jsonify(res)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/imd/district_analysis')
def api_imd_district_analysis():
    """Returns full 1901-2025 historical rainfall & SPI analysis for any district."""
    query = request.args.get('district', '').strip()
    if not query:
        return jsonify({"success": False, "error": "District query required."}), 400

    record = processor.get_district_historical(query)
    if not record:
        return jsonify({"success": False, "error": f"District '{query}' not found in historical database."}), 404

    return jsonify({
        "success": True,
        "district": record
    })

@app.route('/api/imd/point_analysis')
def api_imd_point_analysis():
    """Returns point probe analysis with calculated SPI-1, SPI-3, SPI-12, date range SPI and historical link."""
    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Invalid lat or lon query parameter"}), 400

    target_date = request.args.get('date')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if start_date:
        dt_s = processor.parse_date_flexible(start_date)
        if dt_s:
            start_date = dt_s.strftime("%Y-%m-%d")
    if end_date:
        dt_e = processor.parse_date_flexible(end_date)
        if dt_e:
            end_date = dt_e.strftime("%Y-%m-%d")
    if target_date:
        dt_t = processor.parse_date_flexible(target_date)
        if dt_t:
            target_date = dt_t.strftime("%Y-%m-%d")
    try:
        res = processor.get_point_analysis(
            lat, lon,
            target_date=target_date,
            start_date=start_date,
            end_date=end_date
        )
        try:
            w_info = live_weather.get_live_weather(lat, lon)
            res['live_weather'] = w_info.get('current')
            res['hourly_weather'] = w_info.get('hourly_24h')
        except Exception:
            res['live_weather'] = None
            res['hourly_weather'] = None

        return jsonify({
            "success": True,
            "data": res
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/weather/live')
def api_weather_live():
    """
    Returns real-time live weather parameters (temperature, wind, humidity,
    pressure, clouds, precipitation, weather conditions & 24h hourly forecast)
    for given lat/lon or district name.
    """
    lat_arg = request.args.get('lat')
    lon_arg = request.args.get('lon')
    district = request.args.get('district')

    lat = None
    lon = None
    landmark = None

    if lat_arg and lon_arg:
        try:
            lat = float(lat_arg)
            lon = float(lon_arg)
        except ValueError:
            pass

    if (lat is None or lon is None) and district:
        dist_info = processor.get_district_historical(district)
        if dist_info:
            lat = dist_info.get('center_lat')
            lon = dist_info.get('center_lon')
            landmark = f"{dist_info.get('district_name')}, {dist_info.get('state_name')}"

    if lat is None or lon is None:
        lat = 20.5937
        lon = 78.9629
        landmark = "Central India"

    weather_data = live_weather.get_live_weather(lat, lon)
    if landmark:
        weather_data['landmark'] = landmark
    return jsonify(weather_data)

@app.route('/api/weather/forecast')
def api_weather_forecast():
    """
    Returns high-resolution 7-day (168-hour) weather forecast with hourly steps,
    daily summaries, WMO classifications, and multi-parameter projections
    for given lat/lon or district name.
    """
    lat_arg = request.args.get('lat')
    lon_arg = request.args.get('lon')
    district = request.args.get('district')
    days_arg = request.args.get('days', '7')

    try:
        days = int(days_arg)
    except ValueError:
        days = 7

    lat = None
    lon = None
    landmark = None

    if lat_arg and lon_arg:
        try:
            lat = float(lat_arg)
            lon = float(lon_arg)
        except ValueError:
            pass

    if (lat is None or lon is None) and district:
        dist_info = processor.get_district_historical(district)
        if dist_info:
            lat = dist_info.get('center_lat')
            lon = dist_info.get('center_lon')
            landmark = f"{dist_info.get('district_name')}, {dist_info.get('state_name')}"

    if lat is None or lon is None:
        lat = 20.5937
        lon = 78.9629
        landmark = "Central India"

    forecast_data = live_weather.get_weather_forecast(lat, lon, days=days)
    if landmark:
        forecast_data['landmark'] = landmark
    return jsonify(forecast_data)

@app.route('/api/imd/sync_status')
def api_imd_sync_status():
    """Returns current status of IMD daily automated sync."""
    status = processor.get_sync_status()
    return jsonify({
        "success": True,
        "sync_status": status
    })

@app.route('/api/imd/sync_refresh', methods=['GET', 'POST'])
def api_imd_sync_refresh():
    """On-demand trigger to sync latest IMD daily grids from IMD Pune."""
    force = request.args.get('force', 'false').lower() == 'true'
    lookback = int(request.args.get('days', 10))
    status = processor.daily_sync(force_refresh=force, lookback_days=lookback)
    return jsonify({
        "success": True,
        "message": "IMD Daily Synchronization executed successfully",
        "sync_status": status
    })

@app.route('/api/sync/all', methods=['GET', 'POST'])
def api_sync_all():
    """Triggers unified synchronization across IMD Gridded Rainfall, SPI models, and PMFBY Datasets."""
    force = request.args.get('force', 'false').lower() == 'true'
    lookback = int(request.args.get('days', 10))

    imd_status = processor.daily_sync(force_refresh=force, lookback_days=lookback)
    pmfby_status = pmfby_proc.daily_sync(force_refresh=force)

    dates = processor.get_available_dates()
    latest_date = dates[-1]["date"] if dates else None

    return jsonify({
        "success": True,
        "message": f"All datasets updated successfully. Latest observation: {latest_date}.",
        "latest_date": latest_date,
        "imd_sync": imd_status,
        "pmfby_sync": pmfby_status,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST")
    })

@app.route('/api/grid')
def api_grid():
    """
    Returns gridded rainfall data, statistics, distribution and advisories
    for a single date or cumulative date range.
    """
    mode = request.args.get('mode', 'daily')
    target_date = request.args.get('date')

    available_dates = [d["date"] for d in processor.get_available_dates()]
    if not available_dates and not target_date:
        return jsonify({"success": False, "error": "No IMD data available in database."}), 404

    try:
        if mode == 'accumulate':
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            accum_days = request.args.get('accum_days', type=int)

            if accum_days and target_date:
                dt_target = datetime.datetime.strptime(target_date, "%Y-%m-%d")
                dt_start = dt_target - datetime.timedelta(days=accum_days - 1)
                start_date = dt_start.strftime("%Y-%m-%d")
                end_date = target_date

            if not start_date or not end_date:
                return jsonify({"success": False, "error": "start_date and end_date required for accumulation"}), 400

            matrix, loaded_dates = processor.load_accumulated_grid(start_date, end_date)
            stats = processor.compute_statistics(matrix)
            compressed_grid = processor.get_compressed_grid_payload(matrix)

            return jsonify({
                "success": True,
                "mode": "accumulate",
                "start_date": start_date,
                "end_date": end_date,
                "days_count": len(loaded_dates),
                "loaded_dates": loaded_dates,
                "stats": stats,
                "grid": compressed_grid
            })

        else:
            # Daily mode
            if not target_date:
                target_date = available_dates[-1]

            matrix = processor.load_date_grid(target_date)
            stats = processor.compute_statistics(matrix)
            compressed_grid = processor.get_compressed_grid_payload(matrix)

            return jsonify({
                "success": True,
                "mode": "daily",
                "date": target_date,
                "stats": stats,
                "grid": compressed_grid
            })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route('/api/point')
def api_point():
    """Returns historical multi-day rainfall time series for a clicked point."""
    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Invalid lat or lon query parameter"}), 400

    try:
        res = processor.get_point_timeseries(lat, lon)
        return jsonify({
            "success": True,
            "data": res
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/fetch', methods=['POST'])
def api_fetch():
    """Fetches a date on-demand from IMD Pune servers."""
    data = request.get_json(silent=True) or {}
    date_str = data.get('date', '').strip()

    if not date_str:
        return jsonify({"success": False, "error": "Date is required (YYYY-MM-DD)"}), 400

    try:
        datetime.datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return jsonify({"success": False, "error": "Invalid date format. Use YYYY-MM-DD"}), 400

    success = processor.fetch_imd_data(date_str)
    if success:
        return jsonify({
            "success": True,
            "message": f"Successfully retrieved IMD gridded rainfall for {date_str}",
            "date": date_str
        })
    else:
        return jsonify({
            "success": False,
            "error": f"Failed to download data for {date_str} from IMD. Ensure date is within IMD archives."
        }), 502

@app.route('/api/upload', methods=['POST'])
def api_upload():
    """Uploads a custom IMD .grd binary file."""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "Empty filename"}), 400

    fname = secure_filename(file.filename)
    if not fname.lower().endswith(('.grd', '.bin')):
        return jsonify({"success": False, "error": "Only .grd or .bin files are supported"}), 400

    dest_path = os.path.join(processor.data_dir, fname)
    file.save(dest_path)

    # Invalidate cache
    processor._cache.clear()

    return jsonify({
        "success": True,
        "message": f"Successfully saved {fname}",
        "filename": fname
    })

@app.route('/api/export/csv')
def export_csv():
    """Exports current rainfall grid as CSV download."""
    date_str = request.args.get('date')
    mode = request.args.get('mode', 'daily')

    if mode == 'accumulate':
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        matrix, _ = processor.load_accumulated_grid(start_date, end_date)
        filename = f"IMD_Rainfall_Accumulated_{start_date}_to_{end_date}.csv"
    else:
        matrix = processor.load_date_grid(date_str)
        filename = f"IMD_Rainfall_{date_str}.csv"

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Latitude", "Longitude", "Rainfall_mm", "Category"])

    for r in range(processor.grid['nlat']):
        for c in range(processor.grid['nlon']):
            val = matrix[r, c]
            if not np.isnan(val):
                lat = round(float(processor.lats[r]), 2)
                lon = round(float(processor.lons[c]), 2)
                r_mm = round(float(val), 1)
                cat = processor.get_category_label(r_mm)
                writer.writerow([lat, lon, r_mm, cat])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.route('/api/export/geojson')
def export_geojson():
    """Exports current rainfall grid as GeoJSON download."""
    date_str = request.args.get('date')
    try:
        geojson_data = processor.get_grid_export_geojson(date_str)
        filename = f"IMD_Rainfall_{date_str}.geojson"
        return Response(
            json.dumps(geojson_data),
            mimetype="application/geo+json",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route('/api/india_states')
def get_india_states():
    """Serves the India state boundaries GeoJSON."""
    geojson_path = os.path.join("data", "india_states.geojson")
    if os.path.exists(geojson_path):
        return send_file(geojson_path, mimetype="application/geo+json")
    return jsonify({"type": "FeatureCollection", "features": []})

# ============================================================================
# PMFBY Crop Insurance REST API & Excel Exporter
# ============================================================================
@app.route('/api/pmfby/summary')
def api_pmfby_summary():
    """Returns PMFBY national season-wise summary data (2018 - 2026)."""
    refresh = request.args.get('refresh', 'false').lower() == 'true'
    data = pmfby_proc.get_national_summary(force_refresh=refresh)
    return jsonify({
        "success": True,
        "count": len(data),
        "data": data
    })

@app.route('/api/pmfby/state_report')
def api_pmfby_state_report():
    """Returns state-wise report for a specific year and season."""
    year = request.args.get('year', '2024')
    season = request.args.get('season', '01')
    scheme = request.args.get('scheme', '02')
    data = pmfby_proc.get_state_report(year=year, season_code=season, scheme_code=scheme)
    return jsonify({
        "success": True,
        "year": year,
        "season": season,
        "count": len(data),
        "data": data
    })

@app.route('/api/pmfby/district_report')
def api_pmfby_district_report():
    """Returns district-wise report across states or for a specific state and insurance company."""
    year = request.args.get('year', '2024')
    season = request.args.get('season', '01')
    state_code = request.args.get('state')
    company = request.args.get('company')
    scheme = request.args.get('scheme', '02')
    data = pmfby_proc.get_district_reports(year=year, season_code=season, state_code=state_code, scheme_code=scheme, company_name=company)
    
    # Extract distinct companies present in this year/season for dropdown
    all_dists = pmfby_proc.get_district_reports(year=year, season_code=season, state_code=None, scheme_code=scheme)
    companies = sorted(list(set(d.get('insurance_company_short', 'AIC of India') for d in all_dists if d.get('insurance_company_short'))))
    
    return jsonify({
        "success": True,
        "year": year,
        "season": season,
        "state_code": state_code,
        "company": company,
        "count": len(data),
        "available_companies": companies,
        "data": data
    })

@app.route('/pmfby/companies')
def pmfby_companies_view():
    """Serves the dynamic PMFBY Insurance Company Analytics Dashboard."""
    return render_template('pmfby_companies.html')

@app.route('/api/pmfby/companies')
def api_pmfby_companies():
    """Returns distinct list of all notified PMFBY Insurance Companies."""
    companies = pmfby_proc.get_all_insurance_companies()
    return jsonify({
        "success": True,
        "count": len(companies),
        "data": companies
    })

@app.route('/api/pmfby/company_analytics')
def api_pmfby_company_analytics():
    """
    Returns multi-dimensional Insurance Company performance data split by:
    - year ('all' or specific year)
    - season ('all', '01' Kharif, '02' Rabi)
    - scheme ('all', '02' PMFBY, '04' RWBCIS)
    - level ('company', 'state', 'district')
    - company ('all' or company name)
    - state ('all' or state code)
    - search (text query)
    """
    year = request.args.get('year', 'all')
    season = request.args.get('season', 'all')
    scheme = request.args.get('scheme', 'all')
    level = request.args.get('level', 'company')
    company = request.args.get('company', 'all')
    state = request.args.get('state', 'all')
    search = request.args.get('search', '')

    data = pmfby_proc.get_company_analytics(
        year=year,
        season=season,
        scheme=scheme,
        level=level,
        company=company,
        state_code=state,
        search=search
    )
    return jsonify(data)

@app.route('/api/pmfby/sync_status')
def api_pmfby_sync_status():
    """Returns the current status of PMFBY daily auto-sync."""
    status = pmfby_proc.get_sync_status()
    return jsonify({
        "success": True,
        "sync_status": status
    })

@app.route('/api/pmfby/sync_refresh', methods=['GET', 'POST'])
def api_pmfby_sync_refresh():
    """Executes on-demand check against PMFBY government portal and updates caches."""
    status = pmfby_proc.daily_sync(force_refresh=True)
    return jsonify({
        "success": True,
        "sync_status": status
    })

@app.route('/api/pmfby/export/company_excel')
def api_pmfby_export_company_excel():
    """Generates and downloads customized Insurance Company Excel workbook."""
    year = request.args.get('year', 'all')
    season = request.args.get('season', 'all')
    scheme = request.args.get('scheme', 'all')
    level = request.args.get('level', 'company')
    company = request.args.get('company', 'all')
    state = request.args.get('state', 'all')

    excel_io = pmfby_proc.generate_company_excel(
        year=year,
        season=season,
        scheme=scheme,
        level=level,
        company=company,
        state_code=state
    )

    comp_tag = f"_{company}" if company != 'all' else ""
    yr_tag = f"_{year}" if year != 'all' else "_2018_2026"
    filename = f"PMFBY_Insurance_Company_Analytics{yr_tag}{comp_tag}.xlsx"

    return Response(
        excel_io.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.route('/api/pmfby/export/company_csv')
def api_pmfby_export_company_csv():
    """Generates and downloads CSV for the currently filtered company view."""
    year = request.args.get('year', 'all')
    season = request.args.get('season', 'all')
    scheme = request.args.get('scheme', 'all')
    level = request.args.get('level', 'company')
    company = request.args.get('company', 'all')
    state = request.args.get('state', 'all')
    search = request.args.get('search', '')

    res = pmfby_proc.get_company_analytics(
        year=year,
        season=season,
        scheme=scheme,
        level=level,
        company=company,
        state_code=state,
        search=search
    )
    data = res.get('data', [])

    output = io.StringIO()
    writer = csv.writer(output)

    if level == 'crop':
        writer.writerow([
            "State Name", "District Name", "Crop Name", "Crop Category",
            "Designated Insurance Company", "Year", "Season", "Scheme",
            "Actuarial Premium Rate (%)", "Farmer Share Rate (%)", "Govt Subsidy Rate (%)",
            "Sum Insured (INR/Ha)", "District Aggregate Rate (%)", "District Historical LR (%)", "Company Historical LR (%)"
        ])
        for d in data:
            writer.writerow([
                d.get("state_name"), d.get("district_name"), d.get("crop_name"), d.get("crop_category"),
                d.get("insurance_company_short"), d.get("year"), d.get("season"), d.get("scheme"),
                d.get("actuarial_rate_pct"), d.get("farmer_rate_pct"), d.get("total_subsidy_rate_pct"),
                d.get("sum_insured_per_ha"), d.get("district_premium_rate_pct"), d.get("district_historical_lr_pct"), d.get("company_historical_lr_pct")
            ])
    elif level == 'district':
        writer.writerow([
            "State Name", "District Name", "District Code", "Designated Insurance Company",
            "Season", "Year", "Scheme", "Insurance Units", "Farmers Enrolled",
            "Area Insured (Lakh Ha)", "Sum Insured (Cr INR)", "Gross Premium (Cr INR)",
            "District Premium Rate (%)", "Farmer Share Rate (%)", "Farmer Share (Cr INR)", "Central Subsidy (Cr INR)", "State Subsidy (Cr INR)",
            "Claims Paid (Cr INR)", "Benefited Farmers", "Current Loss Ratio (%)", "District Historical LR (%)"
        ])
        for d in data:
            writer.writerow([
                d.get("state_name"), d.get("district_name"), d.get("district_code"), d.get("insurance_company_short"),
                d.get("season"), d.get("year"), d.get("scheme"), d.get("iu_count"), d.get("farmer_count"),
                d.get("area_insured_lakh_ha"), d.get("sum_insured_crore"), d.get("gross_premium_crore"),
                d.get("district_premium_rate_pct"), d.get("farmer_premium_rate_pct"), d.get("farmer_share_crore"), d.get("goi_share_crore"), d.get("state_share_crore"),
                d.get("claims_paid_crore"), d.get("benefited_farmers"), d.get("loss_ratio_pct"), d.get("historical_loss_ratio_pct")
            ])
    elif level == 'state':
        writer.writerow([
            "State Name", "Designated Insurance Company", "Season", "Year", "Scheme", "Districts Covered",
            "Farmers Enrolled", "Area Insured (Lakh Ha)", "Sum Insured (Cr INR)", "Gross Premium (Cr INR)",
            "State Premium Rate (%)", "Farmer Share (Cr INR)", "Central Subsidy (Cr INR)", "State Subsidy (Cr INR)",
            "Claims Paid (Cr INR)", "Benefited Farmers", "Current Loss Ratio (%)", "Historical Loss Ratio (%)"
        ])
        for d in data:
            writer.writerow([
                d.get("state_name"), d.get("insurance_company_short"), d.get("season"), d.get("year"), d.get("scheme"),
                d.get("districts_count"), d.get("farmer_count"), d.get("area_insured_lakh_ha"), d.get("sum_insured_crore"),
                d.get("gross_premium_crore"), d.get("state_premium_rate_pct"), d.get("farmer_share_crore"), d.get("goi_share_crore"), d.get("state_share_crore"),
                d.get("claims_paid_crore"), d.get("benefited_farmers"), d.get("loss_ratio_pct"), d.get("historical_loss_ratio_pct")
            ])
    else: # company
        writer.writerow([
            "Insurance Company", "Districts Allocated", "Operating States",
            "Farmers Enrolled", "Area Insured (Lakh Ha)", "Sum Insured (Cr INR)",
            "Gross Premium (Cr INR)", "Company Premium Rate (%)", "Farmer Share (Cr INR)", "Central Subsidy (Cr INR)", "State Subsidy (Cr INR)",
            "Claims Settled (Cr INR)", "Benefited Farmers", "Current Loss Ratio (%)", "Historical Loss Ratio (%)"
        ])
        for d in data:
            writer.writerow([
                d.get("company_short"), d.get("districts_count"), d.get("states_count"),
                d.get("farmer_count"), d.get("area_insured_lakh_ha"), d.get("sum_insured_crore"),
                d.get("gross_premium_crore"), d.get("company_premium_rate_pct"), d.get("farmer_share_crore"), d.get("goi_share_crore"), d.get("state_share_crore"),
                d.get("claims_paid_crore"), d.get("benefited_farmers"), d.get("loss_ratio_pct"), d.get("historical_loss_ratio_pct")
            ])

    output.seek(0)
    filename = f"PMFBY_Insurance_{level}_{year}_{season}_{scheme}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.route('/api/pmfby/export/districts_csv')
def api_pmfby_export_districts_csv():
    """Exports district-level data with Insurance Company as CSV download."""
    year = request.args.get('year', '2024')
    season = request.args.get('season', '01')
    state_code = request.args.get('state')
    company = request.args.get('company')
    data = pmfby_proc.get_district_reports(year=year, season_code=season, state_code=state_code, company_name=company)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "State Name", "District Name", "District Code", "Designated Insurance Company",
        "Season", "Year", "Insurance Units",
        "Enrolled Farmers", "Loanee Farmers", "Non-Loanee Farmers", "Area Insured (Lakh Ha)",
        "Sum Insured (Cr INR)", "Gross Premium (Cr INR)", "Farmer Share (Cr INR)",
        "Central Govt Subsidy (Cr INR)", "State Subsidy (Cr INR)",
        "Claims Paid (Cr INR)", "Benefited Farmers", "Loss Ratio (%)"
    ])
    for d in data:
        writer.writerow([
            d["state_name"], d["district_name"], d["district_code"], d.get("insurance_company", "AIC of India"),
            d["season"], d["year"], d["iu_count"],
            d["farmer_count"], d["loanee"], d["non_loanee"], d["area_insured_lakh_ha"],
            d["sum_insured_crore"], d["gross_premium_crore"], d["farmer_share_crore"],
            d["goi_share_crore"], d["state_share_crore"],
            d["claims_paid_crore"], d["benefited_farmers"], d["loss_ratio_pct"]
        ])

    output.seek(0)
    comp_tag = f"_{company}" if company and company != 'all' else ""
    filename = f"PMFBY_Districts_{year}_{season}{comp_tag}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.route('/api/pmfby/export/excel')
def api_pmfby_export_excel():
    """Generates and downloads the multi-sheet PMFBY Excel (.xlsx) file."""
    excel_io = pmfby_proc.generate_excel_workbook()
    filename = "PMFBY_National_Crop_Insurance_Statistics_2018_2026.xlsx"
    return Response(
        excel_io.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.route('/api/pmfby/export/csv')
def api_pmfby_export_csv():
    """Exports national summary as CSV."""
    data = pmfby_proc.get_national_summary()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Season & Year", "Year", "Season", "States", "Districts", "Insurance Units",
        "Enrolled Farmers", "Total Applications", "Loanee Farmers", "Non-Loanee Farmers",
        "Area Insured (Lakh Ha)", "Sum Insured (Cr INR)", "Gross Premium (Cr INR)",
        "Farmer Share (Cr INR)", "Central Govt Subsidy (Cr INR)", "State Subsidy (Cr INR)",
        "Claims Paid (Cr INR)", "Benefited Farmers", "Loss Ratio (%)"
    ])
    for s in data:
        writer.writerow([
            s["display_name"], s["year"], s["season_name"], s["state_count"], s["district_count"], s["iu_count"],
            s["farmer_count"], s["total_applications"], s["loanee"], s["non_loanee"],
            s["area_insured_lakh_ha"], s["sum_insured_crore"], s["gross_premium_crore"],
            s["farmer_premium_crore"], s["goi_subsidy_crore"], s["state_subsidy_crore"],
            s["claims_paid_crore"], s["benefited_farmers"], s["loss_ratio_pct"]
        ])

    output.seek(0)
    filename = "PMFBY_National_Summary.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# ============================================================================
# PMFBY Pricing & Actuarial Tender Review Module
# ============================================================================
@app.route('/pmfby/pricing')
@app.route('/pricing')
def pmfby_pricing_view():
    """PMFBY Actuarial Pricing, Threshold Yield (3B5, 5B7, TM), Multi-Workbook Review & Loading Simulation."""
    return render_template('pmfby_pricing.html')

@app.route('/api/pricing/summary')
@app.route('/api/summary')
def api_pricing_summary():
    return jsonify(pricing_engine.get_national_summary())

@app.route('/api/pricing/companies')
@app.route('/api/companies')
def api_pricing_companies():
    return jsonify(pricing_engine.get_company_pricing_performance())

@app.route('/api/pricing/states')
@app.route('/api/states')
def api_pricing_states():
    return jsonify(pricing_engine.get_state_pricing_profiles())

@app.route('/api/pricing/crops')
@app.route('/api/crops')
def api_pricing_crops():
    return jsonify(pricing_engine.get_crop_category_pricing())

@app.route('/api/pricing/filter-options')
@app.route('/api/filter-options')
def api_pricing_filter_options():
    states = sorted(list({(r.get("state_name") or "").strip() for r in pricing_engine.crop_rates_data if r.get("state_name")}))
    seasons = sorted(list({(r.get("season") or "").strip() for r in pricing_engine.crop_rates_data if r.get("season")}))
    categories = sorted(list({(r.get("crop_category") or "").strip() for r in pricing_engine.crop_rates_data if r.get("crop_category")}))
    years = sorted(list({str(d.get("year", "")) for d in pricing_engine.districts_data if d.get("year")}))
    companies = sorted(list({(d.get("insurance_company_short") or "").strip() for d in pricing_engine.districts_data if d.get("insurance_company_short")}))
    return jsonify({
        "states": states,
        "seasons": seasons,
        "categories": categories,
        "years": years,
        "companies": companies
    })

@app.route('/api/pricing/rates')
@app.route('/api/rates')
def api_pricing_rates():
    query = request.args.get("q", "").lower().strip()
    state = request.args.get("state", "").strip()
    season = request.args.get("season", "").strip()
    category = request.args.get("category", "").strip()
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 25))

    results = []
    for r in pricing_engine.crop_rates_data:
        if state and (r.get("state_name") or "").upper() != state.upper():
            continue
        if season and (r.get("season") or "").upper() != season.upper():
            continue
        if category and (r.get("crop_category") or "").upper() != category.upper():
            continue
        if query:
            crop_name = (r.get("crop_name") or "").lower()
            dist_name = (r.get("district_name") or "").lower()
            st_name = (r.get("state_name") or "").lower()
            if query not in crop_name and query not in dist_name and query not in st_name:
                continue
        results.append(r)

    total_records = len(results)
    start_idx = (page - 1) * per_page
    paginated = results[start_idx : start_idx + per_page]

    return jsonify({
        "total": total_records,
        "page": page,
        "per_page": per_page,
        "total_pages": (total_records + per_page - 1) // per_page,
        "data": paginated
    })

@app.route('/api/pricing/simulate-beed', methods=['POST'])
@app.route('/api/simulate-beed', methods=['POST'])
def api_pricing_simulate_beed():
    data = request.get_json() or {}
    state_name = data.get("state_name")
    year = data.get("year")
    lower_pct = float(data.get("lower_threshold_pct", 80.0)) / 100.0
    upper_pct = float(data.get("upper_threshold_pct", 110.0)) / 100.0

    if "gross_premium_crore" in data and float(data["gross_premium_crore"]) > 0:
        prem = float(data["gross_premium_crore"])
        claims = float(data.get("claims_paid_crore", 0.0))
    else:
        filtered = pricing_engine.districts_data
        if state_name and state_name != "All States":
            filtered = [d for d in filtered if (d.get("state_name") or "").upper() == state_name.upper()]
        if year and year != "All Years":
            filtered = [d for d in filtered if str(d.get("year", "")) == str(year)]
        prem = sum(float(d.get("gross_premium_crore") or 0.0) for d in filtered)
        claims = sum(float(d.get("claims_paid_crore") or 0.0) for d in filtered)

    actual_lr = (claims / prem * 100.0) if prem > 0 else 0.0
    lower_bound = lower_pct * prem
    upper_bound = upper_pct * prem

    if claims < lower_bound:
        refund_to_govt = lower_bound - claims
        govt_tail_liability = 0.0
        insurer_claims_paid = claims
        insurer_retained = prem - claims - refund_to_govt
        band_status = f"Below {int(lower_pct*100)}%: Government Clawback / Refund Zone"
    elif claims <= upper_bound:
        refund_to_govt = 0.0
        govt_tail_liability = 0.0
        insurer_claims_paid = claims
        insurer_retained = prem - claims
        band_status = f"{int(lower_pct*100)}% to {int(upper_pct*100)}%: Full Insurer Risk Corridor"
    else:
        refund_to_govt = 0.0
        govt_tail_liability = claims - upper_bound
        insurer_claims_paid = upper_bound
        insurer_retained = prem - upper_bound
        band_status = f"Above {int(upper_pct*100)}%: Government Tail-Risk Subvention Zone"

    net_fiscal = refund_to_govt - govt_tail_liability

    return jsonify({
        "gross_premium_crore": round(prem, 2),
        "actual_claims_paid_crore": round(claims, 2),
        "actual_loss_ratio_pct": round(actual_lr, 2),
        "lower_threshold_crore": round(lower_bound, 2),
        "upper_threshold_crore": round(upper_bound, 2),
        "lower_pct": round(lower_pct * 100, 1),
        "upper_pct": round(upper_pct * 100, 1),
        "insurer_claims_paid_crore": round(insurer_claims_paid, 2),
        "refund_to_govt_crore": round(refund_to_govt, 2),
        "govt_tail_liability_crore": round(govt_tail_liability, 2),
        "insurer_retained_crore": round(insurer_retained, 2),
        "net_fiscal_benefit_crore": round(net_fiscal, 2),
        "band_status": band_status
    })

@app.route('/api/pricing/calculate-rate', methods=['POST'])
@app.route('/api/calculate-rate', methods=['POST'])
def api_pricing_calculate_rate():
    data = request.get_json() or {}
    season_type = data.get("season_type", "Kharif")
    is_ne_state = bool(data.get("is_ne_state", False))
    is_irrigated = bool(data.get("is_irrigated", False))
    
    sum_insured_ha = float(data.get("sum_insured_ha", 50000.0))
    area_ha = float(data.get("area_ha", 100.0))
    
    burning_cost_pct = float(data.get("burning_cost_pct", 6.5))
    admin_loading_pct = float(data.get("admin_loading_pct", 5.0))
    reinsurance_loading_pct = float(data.get("reinsurance_loading_pct", 10.0))
    catastrophe_loading_pct = float(data.get("catastrophe_loading_pct", 3.0))
    profit_margin_pct = float(data.get("profit_margin_pct", 4.0))

    apr_pct = burning_cost_pct + (burning_cost_pct * (reinsurance_loading_pct + catastrophe_loading_pct) / 100.0) + admin_loading_pct + profit_margin_pct
    apr_pct = round(apr_pct, 2)

    if season_type == "Kharif":
        farmer_cap_pct = 2.0
    elif season_type == "Rabi":
        farmer_cap_pct = 1.5
    else:
        farmer_cap_pct = 5.0

    farmer_rate_pct = min(farmer_cap_pct, apr_pct)
    total_subsidy_pct = max(0.0, apr_pct - farmer_rate_pct)

    goi_apr_cap = 25.0 if is_irrigated else 30.0
    is_capped = apr_pct > goi_apr_cap
    
    goi_base_ratio = 0.90 if is_ne_state else 0.50
    state_base_ratio = 0.10 if is_ne_state else 0.50

    if is_capped:
        subsidizable_by_goi = max(0.0, goi_apr_cap - farmer_rate_pct)
        goi_subsidy_pct = round(subsidizable_by_goi * goi_base_ratio, 2)
        state_subsidy_pct = round(total_subsidy_pct - goi_subsidy_pct, 2)
        excess_state_burden_pct = round(apr_pct - goi_apr_cap, 2)
    else:
        goi_subsidy_pct = round(total_subsidy_pct * goi_base_ratio, 2)
        state_subsidy_pct = round(total_subsidy_pct * state_base_ratio, 2)
        excess_state_burden_pct = 0.0

    total_sum_insured = sum_insured_ha * area_ha
    gross_premium_total = (total_sum_insured * apr_pct) / 100.0
    farmer_premium_total = (total_sum_insured * farmer_rate_pct) / 100.0
    total_subsidy_total = (total_sum_insured * total_subsidy_pct) / 100.0
    goi_subsidy_total = (total_sum_insured * goi_subsidy_pct) / 100.0
    state_subsidy_total = (total_sum_insured * state_subsidy_pct) / 100.0

    return jsonify({
        "apr_pct": apr_pct,
        "farmer_rate_pct": farmer_rate_pct,
        "total_subsidy_pct": round(total_subsidy_pct, 2),
        "goi_subsidy_pct": goi_subsidy_pct,
        "state_subsidy_pct": state_subsidy_pct,
        "is_capped": is_capped,
        "goi_apr_cap_pct": goi_apr_cap,
        "excess_state_burden_pct": excess_state_burden_pct,
        "total_sum_insured_inr": round(total_sum_insured, 2),
        "gross_premium_inr": round(gross_premium_total, 2),
        "farmer_premium_inr": round(farmer_premium_total, 2),
        "total_subsidy_inr": round(total_subsidy_total, 2),
        "goi_subsidy_inr": round(goi_subsidy_total, 2),
        "state_subsidy_inr": round(state_subsidy_total, 2),
        "breakdown_components": {
            "pure_burning_cost": burning_cost_pct,
            "reinsurance_cost": round(burning_cost_pct * reinsurance_loading_pct / 100.0, 2),
            "catastrophe_reserve": round(burning_cost_pct * catastrophe_loading_pct / 100.0, 2),
            "admin_opex": admin_loading_pct,
            "profit_margin": profit_margin_pct
        }
    })

@app.route('/api/pricing/upload-excel', methods=['POST'])
@app.route('/api/upload-excel', methods=['POST'])
def api_pricing_upload_excel():
    uploaded_files = request.files.getlist("files")
    if not uploaded_files or len(uploaded_files) == 0:
        if "file" in request.files:
            uploaded_files = request.files.getlist("file")
        elif len(request.files) > 0:
            uploaded_files = list(request.files.values())
        else:
            return jsonify({"error": "No file part in request."}), 400
    
    valid_files = [f for f in uploaded_files if f and f.filename != ""]
    if not valid_files:
        return jsonify({"error": "No file selected."}), 400

    selected_sheet = request.form.get("sheet") or request.form.get("sheet_name")
    indemnity_param = request.form.get("indemnity") or request.form.get("indemnity_level")
    ty_method = request.form.get("ty_method") or request.form.get("method") or "5b7"
    indemnity_override = None
    if indemnity_param:
        val = float(indemnity_param)
        indemnity_override = val / 100.0 if val > 1.0 else val
    
    try:
        if len(valid_files) == 1:
            file = valid_files[0]
            file_bytes = file.read()
            review = ExcelReviewService.inspect_and_review(file_bytes, file.filename, selected_sheet, indemnity_override=indemnity_override, ty_method=ty_method)
            return jsonify(review)
        else:
            file_items = [(f.read(), f.filename) for f in valid_files]
            review = ExcelReviewService.inspect_and_review_multiple(file_items, selected_sheet, indemnity_override=indemnity_override, ty_method=ty_method)
            return jsonify(review)
    except Exception as e:
        return jsonify({"error": f"Failed to process Excel file(s): {str(e)}"}), 500

@app.route('/api/pricing/review-sample-excel')
@app.route('/api/review-sample-excel')
def api_pricing_review_sample_excel():
    selected_sheet = request.args.get("sheet") or request.args.get("sheet_name") or "Threshold_Yield_Best_5_of_7"
    indemnity_param = request.args.get("indemnity") or request.args.get("indemnity_level")
    ty_method = request.args.get("ty_method") or request.args.get("method") or "5b7"
    indemnity_override = None
    if indemnity_param:
        val = float(indemnity_param)
        indemnity_override = val / 100.0 if val > 1.0 else val

    if not os.path.exists(PRICING_EXCEL_PATH):
        return jsonify({"error": "Sample workbook not found."}), 404

    try:
        with open(PRICING_EXCEL_PATH, "rb") as fp:
            file_bytes = fp.read()
        review = ExcelReviewService.inspect_and_review(file_bytes, "PMFBY_Pricing_Review_2018_2026.xlsx", selected_sheet, indemnity_override=indemnity_override, ty_method=ty_method)
        return jsonify(review)
    except Exception as e:
        return jsonify({"error": f"Failed to process sample Excel: {str(e)}"}), 500

@app.route('/api/pricing/download-excel')
@app.route('/download-excel')
def api_pricing_download_excel():
    if os.path.exists(PRICING_EXCEL_PATH):
        return send_file(
            PRICING_EXCEL_PATH,
            as_attachment=True,
            download_name="PMFBY_Pricing_Review_2018_2026.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    return jsonify({"error": "Workbook not found."}), 404

@app.route('/api/saved-analyses', methods=['GET'])
def api_pricing_list_saved_analyses():
    try:
        items = SavedAnalysisService.list_all()
        return jsonify(items)
    except Exception as e:
        return jsonify({"error": f"Failed to list saved analyses: {str(e)}"}), 500

@app.route('/api/saved-analyses', methods=['POST'])
def api_pricing_save_analysis():
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"error": "No JSON payload provided."}), 400
        name = data.get("name", "")
        notes = data.get("notes", "")
        payload = data.get("payload") or data.get("analysis_data") or data
        meta = SavedAnalysisService.save(name, payload, notes=notes)
        return jsonify({"success": True, "message": "Analysis successfully saved.", "metadata": meta})
    except Exception as e:
        return jsonify({"error": f"Failed to save analysis: {str(e)}"}), 500

@app.route('/api/saved-analyses/<analysis_id>', methods=['GET'])
def api_pricing_get_saved_analysis(analysis_id):
    record = SavedAnalysisService.get(analysis_id)
    if not record:
        return jsonify({"error": f"Analysis '{analysis_id}' not found."}), 404
    return jsonify(record)

@app.route('/api/saved-analyses/<analysis_id>', methods=['DELETE'])
def api_pricing_delete_saved_analysis(analysis_id):
    success = SavedAnalysisService.delete(analysis_id)
    if not success:
        return jsonify({"error": f"Analysis '{analysis_id}' not found or could not be deleted."}), 404
    return jsonify({"success": True, "message": f"Analysis '{analysis_id}' deleted successfully."})


if __name__ == '__main__':
    print("Starting AgriDSS IMD & PMFBY Integrated Server on port 5000...")
    app.run(host='0.0.0.0', port=5000, debug=False)
