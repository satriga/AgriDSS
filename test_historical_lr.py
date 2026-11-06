import os
import glob
import json

CACHE_DIR = "data/pmfby"

def compute_historical_metrics():
    dist_files = glob.glob(os.path.join(CACHE_DIR, "districts_*.json"))
    
    co_hist = {}     # company -> {premium, claims, by_year: {year: {premium, claims}}}
    dist_hist = {}   # (state_code, district_code/name) -> {premium, claims, by_year}
    state_hist = {}  # state_code -> {premium, claims, by_year}
    
    for f in dist_files:
        if "_all.json" in f: continue
        try:
            with open(f, "r", encoding="utf-8") as fp:
                dists = json.load(fp)
                if not isinstance(dists, list): continue
                for d in dists:
                    prem = float(d.get("gross_premium_crore") or 0.0)
                    claims = float(d.get("claims_paid_crore") or 0.0)
                    yr = str(d.get("year", ""))
                    co = d.get("insurance_company_short") or "AIC of India"
                    sc = str(d.get("state_code", ""))
                    dc = str(d.get("district_code", "")) or str(d.get("district_name", ""))
                    
                    # 1. Company
                    if co not in co_hist:
                        co_hist[co] = {"premium": 0.0, "claims": 0.0, "by_year": {}}
                    co_hist[co]["premium"] += prem
                    co_hist[co]["claims"] += claims
                    if yr not in co_hist[co]["by_year"]:
                        co_hist[co]["by_year"][yr] = {"premium": 0.0, "claims": 0.0}
                    co_hist[co]["by_year"][yr]["premium"] += prem
                    co_hist[co]["by_year"][yr]["claims"] += claims
                    
                    # 2. State
                    if sc:
                        if sc not in state_hist:
                            state_hist[sc] = {"premium": 0.0, "claims": 0.0, "by_year": {}}
                        state_hist[sc]["premium"] += prem
                        state_hist[sc]["claims"] += claims
                        if yr not in state_hist[sc]["by_year"]:
                            state_hist[sc]["by_year"][yr] = {"premium": 0.0, "claims": 0.0}
                        state_hist[sc]["by_year"][yr]["premium"] += prem
                        state_hist[sc]["by_year"][yr]["claims"] += claims
                    
                    # 3. District
                    k_d = f"{sc}_{dc}"
                    if k_d not in dist_hist:
                        dist_hist[k_d] = {"premium": 0.0, "claims": 0.0, "by_year": {}}
                    dist_hist[k_d]["premium"] += prem
                    dist_hist[k_d]["claims"] += claims
                    if yr not in dist_hist[k_d]["by_year"]:
                        dist_hist[k_d]["by_year"][yr] = {"premium": 0.0, "claims": 0.0}
                    dist_hist[k_d]["by_year"][yr]["premium"] += prem
                    dist_hist[k_d]["by_year"][yr]["claims"] += claims
        except Exception:
            pass

    print(f"Computed historical metrics for {len(co_hist)} companies, {len(state_hist)} states, {len(dist_hist)} districts")
    print("\nSample Company Historical LR:")
    for co, data in sorted(co_hist.items(), key=lambda x: x[1]["premium"], reverse=True)[:5]:
        p = data["premium"]
        c = data["claims"]
        lr = round(c / p * 100, 1) if p > 0 else 0.0
        print(f"  {co:<20} | Total Prem: Rs.{p:>9,.1f} Cr | Claims: Rs.{c:>9,.1f} Cr | Historical LR: {lr:>5.1f}%")

compute_historical_metrics()
