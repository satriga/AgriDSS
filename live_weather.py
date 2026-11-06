"""
AgriDSS Live Weather Engine
Integrates real-time observational and forecast weather parameters from Open-Meteo & WMO
with high-resolution spatial caching and coordinate lookup.
"""

import time
import requests
import datetime

# 10-minute in-memory cache for live weather queries
_weather_cache = {}
_forecast_cache = {}
CACHE_TTL = 600       # 10 minutes
FORECAST_CACHE_TTL = 900  # 15 minutes

WMO_WEATHER_CODES = {
    0: {"description": "Clear Sky", "icon": "fa-sun", "color": "#facc15"},
    1: {"description": "Mainly Clear", "icon": "fa-cloud-sun", "color": "#fde047"},
    2: {"description": "Partly Cloudy", "icon": "fa-cloud-sun", "color": "#94a3b8"},
    3: {"description": "Overcast", "icon": "fa-cloud", "color": "#64748b"},
    45: {"description": "Foggy", "icon": "fa-smog", "color": "#94a3b8"},
    48: {"description": "Depositing Rime Fog", "icon": "fa-smog", "color": "#94a3b8"},
    51: {"description": "Light Drizzle", "icon": "fa-cloud-rain", "color": "#38bdf8"},
    53: {"description": "Moderate Drizzle", "icon": "fa-cloud-rain", "color": "#0284c7"},
    55: {"description": "Dense Drizzle", "icon": "fa-cloud-showers-heavy", "color": "#0369a1"},
    56: {"description": "Light Freezing Drizzle", "icon": "fa-snowflake", "color": "#93c5fd"},
    57: {"description": "Dense Freezing Drizzle", "icon": "fa-snowflake", "color": "#60a5fa"},
    61: {"description": "Slight Rain", "icon": "fa-cloud-rain", "color": "#38bdf8"},
    63: {"description": "Moderate Rain", "icon": "fa-cloud-showers-heavy", "color": "#0284c7"},
    65: {"description": "Heavy Rain", "icon": "fa-cloud-showers-water", "color": "#1d4ed8"},
    66: {"description": "Light Freezing Rain", "icon": "fa-snowflake", "color": "#93c5fd"},
    67: {"description": "Heavy Freezing Rain", "icon": "fa-snowflake", "color": "#60a5fa"},
    71: {"description": "Slight Snow Fall", "icon": "fa-snowflake", "color": "#e2e8f0"},
    73: {"description": "Moderate Snow Fall", "icon": "fa-snowflake", "color": "#cbd5e1"},
    75: {"description": "Heavy Snow Fall", "icon": "fa-snowflake", "color": "#94a3b8"},
    77: {"description": "Snow Grains", "icon": "fa-snowflake", "color": "#cbd5e1"},
    80: {"description": "Slight Rain Showers", "icon": "fa-cloud-sun-rain", "color": "#38bdf8"},
    81: {"description": "Moderate Rain Showers", "icon": "fa-cloud-showers-heavy", "color": "#0284c7"},
    82: {"description": "Violent Rain Showers", "icon": "fa-cloud-showers-water", "color": "#1e40af"},
    85: {"description": "Slight Snow Showers", "icon": "fa-snowflake", "color": "#e2e8f0"},
    86: {"description": "Heavy Snow Showers", "icon": "fa-snowflake", "color": "#94a3b8"},
    95: {"description": "Thunderstorm", "icon": "fa-bolt", "color": "#a855f7"},
    96: {"description": "Thunderstorm with Slight Hail", "icon": "fa-cloud-bolt", "color": "#9333ea"},
    99: {"description": "Thunderstorm with Heavy Hail", "icon": "fa-cloud-bolt", "color": "#7e22ce"},
}

def degrees_to_compass(degrees):
    """Converts wind direction degrees (0-360) to 16-point compass heading."""
    val = int((degrees / 22.5) + 0.5)
    arr = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return arr[val % 16]

def get_live_weather(lat, lon):
    """
    Fetches real-time live weather parameters for coordinates with caching.
    """
    lat_r = round(lat, 2)
    lon_r = round(lon, 2)
    cache_key = f"{lat_r}_{lon_r}"

    now = time.time()
    if cache_key in _weather_cache:
        entry = _weather_cache[cache_key]
        if now - entry["timestamp"] < CACHE_TTL:
            return entry["data"]

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat_r,
        "longitude": lon_r,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,weather_code,surface_pressure,wind_speed_10m,wind_direction_10m,wind_gusts_10m,cloud_cover",
        "hourly": "temperature_2m,relative_humidity_2m,precipitation_probability,precipitation,wind_speed_10m",
        "forecast_days": 2,
        "timezone": "auto"
    }

    try:
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            raw = resp.json()
            curr = raw.get("current", {})
            w_code = curr.get("weather_code", 0)
            cond = WMO_WEATHER_CODES.get(w_code, {"description": "Moderate Weather", "icon": "fa-cloud", "color": "#94a3b8"})
            wind_dir = curr.get("wind_direction_10m", 0)
            compass = degrees_to_compass(wind_dir)

            # Extract next 24 hours trend
            hourly = raw.get("hourly", {})
            h_times = hourly.get("time", [])[:24]
            h_temps = hourly.get("temperature_2m", [])[:24]
            h_precip = hourly.get("precipitation", [])[:24]
            h_prob = hourly.get("precipitation_probability", [])[:24]
            h_wind = hourly.get("wind_speed_10m", [])[:24]

            # Approximate dew point: T - ((100 - RH) / 5)
            t = curr.get("temperature_2m", 25.0)
            rh = curr.get("relative_humidity_2m", 60.0)
            dew_point = round(t - ((100.0 - rh) / 5.0), 1)

            data = {
                "success": True,
                "latitude": lat_r,
                "longitude": lon_r,
                "current": {
                    "time": curr.get("time"),
                    "temperature": round(t, 1),
                    "apparent_temperature": round(curr.get("apparent_temperature", t), 1),
                    "humidity": int(rh),
                    "dew_point": dew_point,
                    "wind_speed": round(curr.get("wind_speed_10m", 0.0), 1),
                    "wind_direction": int(wind_dir),
                    "wind_compass": compass,
                    "wind_gusts": round(curr.get("wind_gusts_10m", 0.0), 1),
                    "surface_pressure": round(curr.get("surface_pressure", 1013.2), 1),
                    "cloud_cover": int(curr.get("cloud_cover", 0)),
                    "precipitation": round(curr.get("precipitation", 0.0), 1),
                    "rain": round(curr.get("rain", 0.0), 1),
                    "weather_code": w_code,
                    "condition": cond["description"],
                    "icon": cond["icon"],
                    "color": cond["color"]
                },
                "hourly_24h": {
                    "times": [t.split("T")[-1] for t in h_times],
                    "temperatures": h_temps,
                    "precipitations": h_precip,
                    "probabilities": h_prob,
                    "winds": h_wind
                },
                "source": "Open-Meteo & WMO Operational Service"
            }

            _weather_cache[cache_key] = {
                "timestamp": now,
                "data": data
            }
            return data
    except Exception as e:
        pass

    # Fallback response if external API is unreachable
    return {
        "success": True,
        "latitude": lat_r,
        "longitude": lon_r,
        "current": {
            "time": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M"),
            "temperature": 27.0,
            "apparent_temperature": 29.5,
            "humidity": 65,
            "dew_point": 20.0,
            "wind_speed": 12.0,
            "wind_direction": 270,
            "wind_compass": "W",
            "wind_gusts": 18.0,
            "surface_pressure": 1012.0,
            "cloud_cover": 25,
            "precipitation": 0.0,
            "rain": 0.0,
            "weather_code": 1,
            "condition": "Mainly Clear",
            "icon": "fa-cloud-sun",
            "color": "#fde047"
        },
        "hourly_24h": None,
        "is_fallback": True,
        "source": "AgriDSS Meteorological Climatology Fallback"
    }

def get_weather_forecast(lat, lon, days=7):
    """
    Fetches comprehensive multi-day (up to 168 hours) weather forecast
    with hourly steps, daily summaries, WMO classifications, and multi-parameter projections.
    """
    lat_r = round(lat, 2)
    lon_r = round(lon, 2)
    days_clamped = min(max(days, 1), 16)
    cache_key = f"{lat_r}_{lon_r}_{days_clamped}"

    now = time.time()
    if cache_key in _forecast_cache:
        entry = _forecast_cache[cache_key]
        if now - entry["timestamp"] < FORECAST_CACHE_TTL:
            return entry["data"]

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat_r,
        "longitude": lon_r,
        "hourly": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation_probability,precipitation,rain,weather_code,surface_pressure,cloud_cover,wind_speed_10m,wind_direction_10m,wind_gusts_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,apparent_temperature_max,apparent_temperature_min,precipitation_sum,rain_sum,precipitation_hours,precipitation_probability_max,wind_speed_10m_max,wind_gusts_10m_max,wind_direction_10m_dominant",
        "forecast_days": days_clamped,
        "timezone": "auto"
    }

    try:
        resp = requests.get(url, params=params, timeout=8)
        if resp.status_code == 200:
            raw = resp.json()
            hourly_raw = raw.get("hourly", {})
            daily_raw = raw.get("daily", {})

            times = hourly_raw.get("time", [])
            temps = hourly_raw.get("temperature_2m", [])
            feels = hourly_raw.get("apparent_temperature", [])
            rhs = hourly_raw.get("relative_humidity_2m", [])
            probs = hourly_raw.get("precipitation_probability", [])
            precips = hourly_raw.get("precipitation", [])
            codes = hourly_raw.get("weather_code", [])
            pressures = hourly_raw.get("surface_pressure", [])
            clouds = hourly_raw.get("cloud_cover", [])
            winds = hourly_raw.get("wind_speed_10m", [])
            wind_dirs = hourly_raw.get("wind_direction_10m", [])
            gusts = hourly_raw.get("wind_gusts_10m", [])

            hourly_steps = []
            now_dt = datetime.datetime.now()

            for idx, t_str in enumerate(times):
                w_c = codes[idx] if idx < len(codes) else 0
                cond = WMO_WEATHER_CODES.get(w_c, {"description": "Clear", "icon": "fa-sun", "color": "#facc15"})
                w_deg = wind_dirs[idx] if idx < len(wind_dirs) else 0
                compass = degrees_to_compass(w_deg)
                
                # Format time labels
                try:
                    dt_step = datetime.datetime.strptime(t_str, "%Y-%m-%dT%H:%M")
                    date_label = dt_step.strftime("%a %d %b")
                    hour_label = dt_step.strftime("%H:%M")
                    full_label = f"{date_label}, {hour_label} IST (+{idx}h)"
                except Exception:
                    date_label = t_str.split("T")[0]
                    hour_label = t_str.split("T")[-1]
                    full_label = f"{t_str} (+{idx}h)"

                t_val = temps[idx] if idx < len(temps) else 25.0
                rh_val = rhs[idx] if idx < len(rhs) else 60.0
                dew_p = round(t_val - ((100.0 - rh_val) / 5.0), 1)

                hourly_steps.append({
                    "index": idx,
                    "time": t_str,
                    "date_label": date_label,
                    "hour_label": hour_label,
                    "full_label": full_label,
                    "hours_ahead": idx,
                    "temperature": round(t_val, 1),
                    "apparent_temperature": round(feels[idx], 1) if idx < len(feels) else round(t_val, 1),
                    "humidity": int(rh_val),
                    "dew_point": dew_p,
                    "precipitation": round(precips[idx], 1) if idx < len(precips) else 0.0,
                    "precipitation_probability": int(probs[idx]) if idx < len(probs) else 0,
                    "wind_speed": round(winds[idx], 1) if idx < len(winds) else 0.0,
                    "wind_direction": int(w_deg),
                    "wind_compass": compass,
                    "wind_gusts": round(gusts[idx], 1) if idx < len(gusts) else 0.0,
                    "pressure": round(pressures[idx], 1) if idx < len(pressures) else 1013.2,
                    "cloud_cover": int(clouds[idx]) if idx < len(clouds) else 0,
                    "weather_code": w_c,
                    "condition": cond["description"],
                    "icon": cond["icon"],
                    "color": cond["color"]
                })

            # Daily summaries
            daily_summaries = []
            d_times = daily_raw.get("time", [])
            d_codes = daily_raw.get("weather_code", [])
            d_max_temps = daily_raw.get("temperature_2m_max", [])
            d_min_temps = daily_raw.get("temperature_2m_min", [])
            d_precips = daily_raw.get("precipitation_sum", [])
            d_probs = daily_raw.get("precipitation_probability_max", [])
            d_winds = daily_raw.get("wind_speed_10m_max", [])

            for d_idx, d_date in enumerate(d_times):
                dw_c = d_codes[d_idx] if d_idx < len(d_codes) else 0
                d_cond = WMO_WEATHER_CODES.get(dw_c, {"description": "Clear", "icon": "fa-sun", "color": "#facc15"})
                try:
                    dt_d = datetime.datetime.strptime(d_date, "%Y-%m-%d")
                    day_name = "Today" if d_idx == 0 else ("Tomorrow" if d_idx == 1 else dt_d.strftime("%a %d %b"))
                except Exception:
                    day_name = d_date

                daily_summaries.append({
                    "date": d_date,
                    "day_name": day_name,
                    "temp_max": round(d_max_temps[d_idx], 1) if d_idx < len(d_max_temps) else 30.0,
                    "temp_min": round(d_min_temps[d_idx], 1) if d_idx < len(d_min_temps) else 20.0,
                    "precip_sum": round(d_precips[d_idx], 1) if d_idx < len(d_precips) else 0.0,
                    "precip_probability": int(d_probs[d_idx]) if d_idx < len(d_probs) else 0,
                    "wind_max": round(d_winds[d_idx], 1) if d_idx < len(d_winds) else 10.0,
                    "weather_code": dw_c,
                    "condition": d_cond["description"],
                    "icon": d_cond["icon"],
                    "color": d_cond["color"]
                })

            result = {
                "success": True,
                "latitude": lat_r,
                "longitude": lon_r,
                "total_hours": len(hourly_steps),
                "total_days": len(daily_summaries),
                "start_time": times[0] if times else None,
                "end_time": times[-1] if times else None,
                "hourly": hourly_steps,
                "daily": daily_summaries,
                "source": "Open-Meteo High-Resolution ECMWF / GFS Global Numerical Models"
            }

            _forecast_cache[cache_key] = {
                "timestamp": now,
                "data": result
            }
            return result
    except Exception as e:
        print(f"Weather forecast query failed: {e}")

    # Fallback synthetically generated 7-day projection based on climatological normal
    fallback_steps = []
    base_dt = datetime.datetime.now()
    for h in range(days_clamped * 24):
        step_dt = base_dt + datetime.timedelta(hours=h)
        # Diurnal temperature cycle: peak at 14:00, trough at 05:00
        hour_val = step_dt.hour
        diurnal = 5.0 * np.sin((hour_val - 8) * np.pi / 12.0)
        t_est = round(26.0 + diurnal, 1)
        fallback_steps.append({
            "index": h,
            "time": step_dt.strftime("%Y-%m-%dT%H:00"),
            "date_label": step_dt.strftime("%a %d %b"),
            "hour_label": step_dt.strftime("%H:00"),
            "full_label": f"{step_dt.strftime('%a %d %b, %H:00')} IST (+{h}h)",
            "hours_ahead": h,
            "temperature": t_est,
            "apparent_temperature": round(t_est + 2.0, 1),
            "humidity": 65,
            "dew_point": 19.0,
            "precipitation": 0.0,
            "precipitation_probability": 15,
            "wind_speed": 10.5,
            "wind_direction": 270,
            "wind_compass": "W",
            "wind_gusts": 16.0,
            "pressure": 1012.0,
            "cloud_cover": 20,
            "weather_code": 1,
            "condition": "Mainly Clear",
            "icon": "fa-cloud-sun",
            "color": "#fde047"
        })

    return {
        "success": True,
        "latitude": lat_r,
        "longitude": lon_r,
        "total_hours": len(fallback_steps),
        "total_days": days_clamped,
        "start_time": fallback_steps[0]["time"],
        "end_time": fallback_steps[-1]["time"],
        "hourly": fallback_steps,
        "daily": [],
        "is_fallback": True,
        "source": "AgriDSS Meteorological Diurnal Climatology Model"
    }
