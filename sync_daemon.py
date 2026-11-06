"""
AgriDSS Automated Daily Synchronization Daemon
Handles recurring automated synchronization for:
1. IMD Daily Gridded Rainfall (0.25° binary .grd files from IMD Pune)
2. SPI (Standardized Precipitation Index) Gridded Calculation Models
3. PMFBY & RWBCIS Crop Insurance National Analytics and District Schemes
4. Live Weather & Climatology Normal Baselines
"""

import os
import sys
import time
import json
import logging
import argparse
import datetime
from imd_processor import IMDProcessor
from pmfby_processor import PMFBYProcessor

# Set up logging
LOG_DIR = os.path.join(os.path.dirname(__file__), "data", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "sync_history.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

def run_sync_cycle(lookback_days=10, force=False):
    """Executes a full synchronization cycle across all AgriDSS data streams."""
    logging.info("==================================================================")
    logging.info("Starting AgriDSS Automated Synchronization Cycle...")
    logging.info(f"Target: IMD Gridded Rainfall (Lookback: {lookback_days}d) & PMFBY National Datasets")

    summary = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
        "imd": {},
        "pmfby": {},
        "success": True
    }

    # 1. Sync IMD Gridded Rainfall
    try:
        imd_proc = IMDProcessor(data_dir="data/grd")
        imd_status = imd_proc.daily_sync(force_refresh=force, lookback_days=lookback_days)
        summary["imd"] = imd_status
        downloaded = imd_status.get("downloaded_dates", [])
        logging.info(f"IMD Gridded Sync Complete: {len(downloaded)} new date(s) downloaded. Latest date: {imd_status.get('latest_date')}")
        if downloaded:
            logging.info(f"New IMD Grids: {', '.join(downloaded)}")
    except Exception as e:
        logging.error(f"IMD Gridded Sync Error: {e}", exc_info=True)
        summary["imd"] = {"error": str(e)}
        summary["success"] = False

    # 2. Sync PMFBY Crop Insurance Data
    try:
        pmfby_proc = PMFBYProcessor(cache_dir="data/pmfby")
        pmfby_status = pmfby_proc.daily_sync(force_refresh=force)
        summary["pmfby"] = pmfby_status
        logging.info(f"PMFBY Daily Sync Complete: {pmfby_status.get('message')}")
    except Exception as e:
        logging.error(f"PMFBY Sync Error: {e}", exc_info=True)
        summary["pmfby"] = {"error": str(e)}
        summary["success"] = False

    # Save Unified Sync State
    unified_file = os.path.join("data", "grd", "unified_sync_status.json")
    try:
        with open(unified_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
    except Exception as e:
        logging.warning(f"Could not write unified sync status: {e}")

    logging.info("AgriDSS Automated Synchronization Cycle Finished.")
    logging.info("==================================================================")
    return summary

def main():
    parser = argparse.ArgumentParser(description="AgriDSS Automated Daily Synchronization Daemon")
    parser.add_argument("--once", action="store_true", help="Run sync once and exit")
    parser.add_argument("--force", action="store_true", help="Force re-download of existing recent files")
    parser.add_argument("--days", type=int, default=10, help="Number of lookback days to check for missing IMD grids")
    parser.add_argument("--interval", type=int, default=3600, help="Seconds between periodic loop checks (default: 3600s / 1 hour)")
    args = parser.parse_args()

    if args.once:
        run_sync_cycle(lookback_days=args.days, force=args.force)
        sys.exit(0)

    logging.info(f"AgriDSS Auto-Sync Daemon started in persistent mode (interval: {args.interval}s)...")
    # Immediate initial run
    run_sync_cycle(lookback_days=args.days, force=args.force)

    while True:
        try:
            time.sleep(args.interval)
            now = datetime.datetime.now()
            # IMD 08:30 IST release window (08:30 - 10:30) and evening catch-up (20:30 - 22:30)
            is_release_window = now.hour in [8, 9, 10, 20, 21, 22]
            logging.info(f"Periodic check at {now.strftime('%H:%M:%S')} (Release window active: {is_release_window})")
            run_sync_cycle(lookback_days=args.days, force=False)
        except KeyboardInterrupt:
            logging.info("Daemon interrupted by operator. Exiting.")
            break
        except Exception as e:
            logging.error(f"Unexpected daemon error: {e}", exc_info=True)
            time.sleep(60)

if __name__ == "__main__":
    main()
