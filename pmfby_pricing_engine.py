"""
PMFBY Pricing Review & Actuarial Analysis Engine
================================================
Comprehensive pricing review module for Pradhan Mantri Fasal Bima Yojana (PMFBY).
Includes:
1. Actuarial Premium Rate (APR) vs Burning Cost analysis
2. 8-Year Loss Ratio and Financial Underwriting Metrics (2018-2026)
3. Company and State pricing adequacy evaluations
4. Beed Model (80:110) & Cup-and-Cap (60:130) financial simulation
"""

import os
import glob
import json
from typing import Dict, List, Any, Optional

DATA_DIR = r"D:\AGRIDSS\data\pmfby"

class PMFBYPricingEngine:
    def __init__(self, data_dir: str = DATA_DIR):
        self.data_dir = data_dir
        self.districts_data: List[Dict[str, Any]] = []
        self.crop_rates_data: List[Dict[str, Any]] = []
        self._load_data()

    def _load_data(self):
        """Loads district records and crop rates from PMFBY caches."""
        dist_files = glob.glob(os.path.join(self.data_dir, "districts_*.json"))
        for f in dist_files:
            if "_all.json" in f:
                continue
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    records = json.load(fp)
                    if isinstance(records, list):
                        self.districts_data.extend(records)
            except Exception:
                pass

        rate_path = os.path.join(self.data_dir, "crop_district_rates.json")
        if os.path.exists(rate_path):
            try:
                with open(rate_path, "r", encoding="utf-8") as fp:
                    self.crop_rates_data = json.load(fp)
            except Exception:
                pass

    def get_national_summary(self) -> Dict[str, Any]:
        """Calculates national time-series and aggregate financial totals."""
        by_year: Dict[str, Dict[str, float]] = {}
        total_prem = 0.0
        total_claims = 0.0
        total_farmers = 0.0

        for d in self.districts_data:
            yr = str(d.get("year", ""))
            prem = float(d.get("gross_premium_crore") or 0.0)
            claims = float(d.get("claims_paid_crore") or 0.0)
            farmers = float(d.get("farmer_applications") or d.get("farmer_count") or 0.0)

            total_prem += prem
            total_claims += claims
            total_farmers += farmers

            if yr:
                if yr not in by_year:
                    by_year[yr] = {"gross_premium": 0.0, "claims_paid": 0.0, "farmers": 0.0}
                by_year[yr]["gross_premium"] += prem
                by_year[yr]["claims_paid"] += claims
                by_year[yr]["farmers"] += farmers

        yearly_list = []
        for y in sorted(by_year.keys()):
            p = by_year[y]["gross_premium"]
            c = by_year[y]["claims_paid"]
            lr = (c / p * 100) if p > 0 else 0.0
            yearly_list.append({
                "year": y,
                "gross_premium_crore": round(p, 2),
                "claims_paid_crore": round(c, 2),
                "farmer_applications": int(by_year[y]["farmers"]),
                "loss_ratio_pct": round(lr, 2)
            })

        overall_lr = (total_claims / total_prem * 100) if total_prem > 0 else 0.0
        return {
            "total_gross_premium_crore": round(total_prem, 2),
            "total_claims_paid_crore": round(total_claims, 2),
            "overall_loss_ratio_pct": round(overall_lr, 2),
            "total_farmer_applications": int(total_farmers),
            "yearly_trend": yearly_list
        }

    def get_company_pricing_performance(self) -> List[Dict[str, Any]]:
        """Aggregates underwriting performance and loss ratios by insurance company."""
        by_co: Dict[str, Dict[str, Any]] = {}

        for d in self.districts_data:
            co = d.get("insurance_company_short") or "AIC of India"
            prem = float(d.get("gross_premium_crore") or 0.0)
            claims = float(d.get("claims_paid_crore") or 0.0)
            farmers = float(d.get("farmer_applications") or d.get("farmer_count") or 0.0)

            if co not in by_co:
                by_co[co] = {"gross_premium": 0.0, "claims_paid": 0.0, "farmers": 0.0}
            by_co[co]["gross_premium"] += prem
            by_co[co]["claims_paid"] += claims
            by_co[co]["farmers"] += farmers

        results = []
        tot_prem = sum(v["gross_premium"] for v in by_co.values())
        for co, v in by_co.items():
            p = v["gross_premium"]
            c = v["claims_paid"]
            lr = (c / p * 100) if p > 0 else 0.0
            mkt_share = (p / tot_prem * 100) if tot_prem > 0 else 0.0
            
            # Pricing Adequacy status
            if lr > 100:
                verdict = "Severe Loss / Underpriced"
            elif lr > 75:
                verdict = "Elevated Risk / Marginal"
            elif lr >= 50:
                verdict = "Healthy / Technically Sound"
            else:
                verdict = "Highly Profitable / Conservative"

            results.append({
                "insurance_company": co,
                "gross_premium_crore": round(p, 2),
                "market_share_pct": round(mkt_share, 2),
                "claims_paid_crore": round(c, 2),
                "farmer_applications": int(v["farmers"]),
                "loss_ratio_pct": round(lr, 2),
                "pricing_verdict": verdict
            })

        results.sort(key=lambda x: x["gross_premium_crore"], reverse=True)
        return results

    def get_state_pricing_profiles(self) -> List[Dict[str, Any]]:
        """Aggregates state-wise gross premiums, claims, loss ratios, and average APRs."""
        by_st: Dict[str, Dict[str, Any]] = {}

        for d in self.districts_data:
            st = d.get("state_name") or str(d.get("state_code", "Unknown"))
            prem = float(d.get("gross_premium_crore") or 0.0)
            claims = float(d.get("claims_paid_crore") or 0.0)
            farmers = float(d.get("farmer_applications") or d.get("farmer_count") or 0.0)

            if st not in by_st:
                by_st[st] = {"gross_premium": 0.0, "claims_paid": 0.0, "farmers": 0.0}
            by_st[st]["gross_premium"] += prem
            by_st[st]["claims_paid"] += claims
            by_st[st]["farmers"] += farmers

        # Calculate avg APR per state from crop rates data
        state_aprs: Dict[str, List[float]] = {}
        for r in self.crop_rates_data:
            s_name = (r.get("state_name") or "").upper().strip()
            apr = float(r.get("actuarial_rate_pct") or 0.0)
            if s_name and apr > 0:
                if s_name not in state_aprs:
                    state_aprs[s_name] = []
                state_aprs[s_name].append(apr)

        results = []
        for st, v in by_st.items():
            p = v["gross_premium"]
            c = v["claims_paid"]
            lr = (c / p * 100) if p > 0 else 0.0
            st_key = st.upper().strip()
            apr_list = state_aprs.get(st_key, [])
            avg_apr = (sum(apr_list) / len(apr_list)) if apr_list else 0.0

            results.append({
                "state_name": st,
                "gross_premium_crore": round(p, 2),
                "claims_paid_crore": round(c, 2),
                "loss_ratio_pct": round(lr, 2),
                "farmer_applications": int(v["farmers"]),
                "avg_notified_apr_pct": round(avg_apr, 2) if avg_apr else None
            })

        results.sort(key=lambda x: x["gross_premium_crore"], reverse=True)
        return results

    def get_crop_category_pricing(self) -> List[Dict[str, Any]]:
        """Analyzes actuarial rates, farmer shares, and subsidies across crop categories."""
        by_cat: Dict[str, List[Dict[str, float]]] = {}

        for r in self.crop_rates_data:
            cat = r.get("crop_category", "Agriculture")
            apr = float(r.get("actuarial_rate_pct") or 0.0)
            fr = float(r.get("farmer_rate_pct") or 0.0)
            sub = float(r.get("total_subsidy_rate_pct") or 0.0)
            si = float(r.get("sum_insured_per_ha") or 0.0)

            if cat not in by_cat:
                by_cat[cat] = []
            by_cat[cat].append({"apr": apr, "fr": fr, "sub": sub, "si": si})

        results = []
        for cat, rows in by_cat.items():
            n = len(rows)
            avg_apr = sum(x["apr"] for x in rows) / n
            avg_fr = sum(x["fr"] for x in rows) / n
            avg_sub = sum(x["sub"] for x in rows) / n
            avg_si = sum(x["si"] for x in rows) / n

            results.append({
                "crop_category": cat,
                "notifications_count": n,
                "avg_actuarial_rate_pct": round(avg_apr, 2),
                "avg_farmer_rate_pct": round(avg_fr, 2),
                "avg_govt_subsidy_pct": round(avg_sub, 2),
                "avg_sum_insured_per_ha": round(avg_si, 2)
            })

        results.sort(key=lambda x: x["notifications_count"], reverse=True)
        return results

    def simulate_beed_model(self, state_name: Optional[str] = None, year: Optional[str] = None) -> Dict[str, Any]:
        """
        Simulates the Beed Model (80:110 profit-sharing and loss-capping formula):
        - Claims < 80% of Premium: Insurer retains 20% for expenses & profit, refunds (80% - Claims) to Government.
        - Claims 80% to 110%: Insurer pays all claims, no refund or liability for Government.
        - Claims > 110%: Insurer loss capped at 110%, Government / pool pays excess claims (Claims - 110%).
        """
        filtered = self.districts_data
        if state_name:
            filtered = [d for d in filtered if (d.get("state_name") or "").upper() == state_name.upper()]
        if year:
            filtered = [d for d in filtered if str(d.get("year", "")) == str(year)]

        prem = sum(float(d.get("gross_premium_crore") or 0.0) for d in filtered)
        claims = sum(float(d.get("claims_paid_crore") or 0.0) for d in filtered)
        actual_lr = (claims / prem * 100) if prem > 0 else 0.0

        lower_bound = 0.80 * prem
        upper_bound = 1.10 * prem

        if claims < lower_bound:
            refund_to_govt = lower_bound - claims
            govt_liability = 0.0
            insurer_claims_paid = claims
            insurer_retention = 0.20 * prem
        elif claims <= upper_bound:
            refund_to_govt = 0.0
            govt_liability = 0.0
            insurer_claims_paid = claims
            insurer_retention = prem - claims
        else:
            refund_to_govt = 0.0
            govt_liability = claims - upper_bound
            insurer_claims_paid = upper_bound
            insurer_retention = prem - upper_bound  # -0.10 * prem

        return {
            "filter_state": state_name or "All States",
            "filter_year": year or "All Years (2018-2026)",
            "gross_premium_crore": round(prem, 2),
            "actual_claims_paid_crore": round(claims, 2),
            "actual_loss_ratio_pct": round(actual_lr, 2),
            "beed_insurer_claims_burden_crore": round(insurer_claims_paid, 2),
            "beed_refund_to_government_crore": round(refund_to_govt, 2),
            "beed_government_extra_liability_crore": round(govt_liability, 2),
            "beed_insurer_net_retention_crore": round(insurer_retention, 2),
            "net_fiscal_benefit_to_govt_crore": round(refund_to_govt - govt_liability, 2)
        }

if __name__ == "__main__":
    engine = PMFBYPricingEngine()
    print("=== PMFBY PRICING ENGINE TEST ===")
    summary = engine.get_national_summary()
    print(f"Total Premium: Rs. {summary['total_gross_premium_crore']:,.2f} Cr")
    print(f"Total Claims: Rs. {summary['total_claims_paid_crore']:,.2f} Cr")
    print(f"Overall LR: {summary['overall_loss_ratio_pct']}%")

    print("\n--- Beed 80:110 Model Simulation (National Portfolio) ---")
    beed = engine.simulate_beed_model()
    for k, v in beed.items():
        print(f"  {k}: {v}")
