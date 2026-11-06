"""
PMFBY Excel Pricing & Actuarial Review Service
==============================================
Intelligently inspects, parses, and reviews uploaded Excel workbooks:
- Multi-sheet detection & automatic header identification
- Actuarial loss ratio & underwriting adequacy evaluation
- Beed 80:110 profit-sharing & loss-capping simulation
- Three Threshold Yield (TY) Methodologies:
    1. 3B5: Best 3 out of preceding 5 years multiplied by indemnity level
    2. 5B7: Best 5 out of preceding 7 years multiplied by indemnity level (Standard PMFBY)
    3. TM:  Last 10 years yield minus 2 worst years (8-year trimmed mean) multiplied by indemnity level
- Dynamic Crop-Wise and Cluster-Wise Threshold Yield & Sum Insured aggregation
- Anomaly, outlier, and regulatory capping alerts
- Structured tabular data extraction with column mapping
"""

import io
import re
import openpyxl
from typing import Dict, List, Any, Optional, Tuple

def clean_float(val: Any) -> Optional[float]:
    """Safely converts string/number/currency format into a float."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "null", "-", "n/a"):
        return None
    # Remove currency symbols (₹, $, Rs.), commas, %, spaces
    s = re.sub(r"[₹\$,\s%]", "", s)
    s = re.sub(r"(?i)\bcr\b|\bcrore\b|\blakh\b", "", s)
    # Handle negative in parentheses e.g. (123.45)
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return None

def find_header_row(rows: List[List[Any]]) -> int:
    """Detects the index of the most probable tabular header row."""
    best_idx = 0
    best_score = -1
    for idx, r in enumerate(rows[:20]):
        non_empty = [c for c in r if c is not None and str(c).strip()]
        if len(non_empty) < 2:
            continue
        score = len(non_empty)
        row_text = " ".join(str(c).lower() for c in non_empty)
        keywords = [
            "year", "company", "state", "district", "crop", "premium", "prem", 
            "claim", "claims", "loss ratio", "apr", "rate", "subsidy", 
            "sum insured", "farmer", "season", "verdict", "share", "threshold",
            "benchmark", "indemnity", "yield"
        ]
        matches = sum(1 for kw in keywords if kw in row_text)
        score += matches * 6
        if score > best_score:
            best_score = score
            best_idx = idx
    return best_idx

def identify_columns(headers: List[str]) -> Dict[str, Optional[int]]:
    """Maps semantic actuarial roles to column indices."""
    col_map = {
        "entity": None,
        "premium": None,
        "claims": None,
        "loss_ratio": None,
        "apr": None,
        "farmer_rate": None,
        "subsidy_rate": None,
        "sum_insured": None,
        "sum_insured_total": None,
        "si_per_ha": None,
        "farmers_count": None,
        "actual_yield": None,
        "indemnity": None,
        "cluster": None,
        "state": None,
        "district": None,
        "crop": None,
        "season": None
    }

    lower_headers = [str(h).lower() for h in headers]

    # Cluster Column
    for idx, h in enumerate(lower_headers):
        if any(k in h for k in ["cluster", "bidding cluster", "cluster no", "cluster_name", "zone"]):
            col_map["cluster"] = idx
            break

    # State Column
    for idx, h in enumerate(lower_headers):
        if "state" in h:
            col_map["state"] = idx
            break

    # District Column (exclude sub-district)
    for idx, h in enumerate(lower_headers):
        if ("district" in h or "dist" in h) and "sub" not in h:
            col_map["district"] = idx
            break
    if col_map["district"] is None:
        for idx, h in enumerate(lower_headers):
            if "district" in h or "dist" in h:
                col_map["district"] = idx
                break

    # Crop Column
    for idx, h in enumerate(lower_headers):
        if "crop" in h or "commodity" in h:
            col_map["crop"] = idx
            break

    # Season Column
    for idx, h in enumerate(lower_headers):
        if "season" in h:
            col_map["season"] = idx
            break

    # Entity column (State, Company, Crop, Year, District, Scope)
    for idx, h in enumerate(lower_headers):
        if any(k in h for k in ["crop", "district", "state", "company", "year", "scope", "season"]):
            col_map["entity"] = idx
            break
    if col_map["entity"] is None and len(headers) > 0:
        col_map["entity"] = 0

    # Premium
    for idx, h in enumerate(lower_headers):
        if any(k in h for k in ["gross premium", "gwp", "premium ("]):
            col_map["premium"] = idx
            break
    if col_map["premium"] is None:
        for idx, h in enumerate(lower_headers):
            if "premium" in h or "prem" in h:
                col_map["premium"] = idx
                break

    # Claims
    for idx, h in enumerate(lower_headers):
        if any(k in h for k in ["claims paid", "claims settled", "actual claims", "claims ("]):
            col_map["claims"] = idx
            break
    if col_map["claims"] is None:
        for idx, h in enumerate(lower_headers):
            if "claim" in h:
                col_map["claims"] = idx
                break

    # Loss Ratio
    for idx, h in enumerate(lower_headers):
        if any(k in h for k in ["loss ratio", "lr (", "lr%", "actual lr"]):
            col_map["loss_ratio"] = idx
            break

    # APR
    for idx, h in enumerate(lower_headers):
        if any(k in h for k in ["actuarial rate", "apr", "quoted rate"]):
            col_map["apr"] = idx
            break

    # Farmer Rate
    for idx, h in enumerate(lower_headers):
        if any(k in h for k in ["farmer rate", "farmer share"]):
            col_map["farmer_rate"] = idx
            break

    # Subsidy Rate
    for idx, h in enumerate(lower_headers):
        if any(k in h for k in ["subsidy", "govt share"]):
            col_map["subsidy_rate"] = idx
            break

    # Sum Insured Per Hectare
    for idx, h in enumerate(lower_headers):
        if any(k in h for k in ["si per ha", "si/ha", "si_per_ha", "si (inr/ha)", "sum insured per ha", "si_ha"]):
            col_map["si_per_ha"] = idx
            break

    # Total Sum Insured
    for idx, h in enumerate(lower_headers):
        if any(k in h for k in ["sum insured (inr)", "sum insured (rs", "total sum insured", "total_sum_insured", "sum insured"]):
            if col_map.get("si_per_ha") != idx:
                col_map["sum_insured_total"] = idx
                break

    # Fallback generic sum_insured
    if col_map["sum_insured_total"] is not None:
        col_map["sum_insured"] = col_map["sum_insured_total"]
    elif col_map["si_per_ha"] is not None:
        col_map["sum_insured"] = col_map["si_per_ha"]
    else:
        for idx, h in enumerate(lower_headers):
            if "sum" in h and "insured" in h:
                col_map["sum_insured"] = idx
                break

    # Actual / Current Yield
    for idx, h in enumerate(lower_headers):
        if any(k in h for k in ["actual season yield", "actual yield", "current yield", "assessed yield", "cce yield"]):
            col_map["actual_yield"] = idx
            break

    # Indemnity Level
    for idx, h in enumerate(lower_headers):
        if any(k in h for k in ["indemnity level", "indemnity", "il (%)", "il%"]):
            col_map["indemnity"] = idx
            break

    return col_map

def identify_yield_series_columns(headers: List[str]) -> List[int]:
    """Identifies columns that represent historical yield series (e.g. 2011 to 2021, 2017 to 2023, or Yield_1 to Yield_7)."""
    yield_cols = []
    for idx, h in enumerate(headers):
        h_str = str(h).strip().lower()
        # Exclude non-historical yield columns
        if any(skip in h_str for skip in [
            "actual", "current", "assessed", "threshold", "ty", "benchmark", "shortfall", 
            "loss", "calamity", "area", "insured", "rate", "prem", "claim", "sown", "payout"
        ]):
            continue
        # Check for 4-digit years (e.g. '2011', '2011 Yield', 'Yield 2011', 'Yield_2011')
        if re.search(r"\b(19|20)\d{2}\b", h_str):
            yield_cols.append(idx)
        elif any(k in h_str for k in [
            "yield_20", "yield_19", "yield_y", "cce_yield_", "yield 1", "yield 2", 
            "yield 3", "yield 4", "yield 5", "yield 6", "yield 7", "y1", "y2", "y3", "y4", "y5", "y6", "y7"
        ]):
            yield_cols.append(idx)
    return yield_cols

def compute_ty_methods(yield_pairs: List[Tuple[str, float]], il_val: float, active_method: str = "5b7") -> Dict[str, Any]:
    """
    Computes Benchmark Yield and Threshold Yield under 3 PMFBY methodologies:
    - 5B7: Best 5 out of preceding 7 years
    - 3B5: Best 3 out of preceding 5 years
    - TM:  Last 10 years yield minus 2 worst calamity years (8-year trimmed mean)
    """
    active_method = (active_method or "5b7").strip().lower()

    # 1. 5B7: Preceding up to 7 years, take best 5
    p7 = yield_pairs[-7:] if len(yield_pairs) >= 7 else yield_pairs
    s7 = sorted(p7, key=lambda x: x[1], reverse=True)
    b5 = s7[:5]
    d7 = s7[5:]
    bm_5b7 = round(sum(p[1] for p in b5) / len(b5), 2) if b5 else 0.0
    ty_5b7 = round(bm_5b7 * il_val, 2)

    # 2. 3B5: Preceding up to 5 years, take best 3
    p5 = yield_pairs[-5:] if len(yield_pairs) >= 5 else yield_pairs
    s5 = sorted(p5, key=lambda x: x[1], reverse=True)
    b3 = s5[:3]
    d5 = s5[3:]
    bm_3b5 = round(sum(p[1] for p in b3) / len(b3), 2) if b3 else 0.0
    ty_3b5 = round(bm_3b5 * il_val, 2)

    # 3. TM: Preceding up to 10 years, subtract 2 worst years (trimmed mean)
    p10 = yield_pairs[-10:] if len(yield_pairs) >= 10 else yield_pairs
    s10 = sorted(p10, key=lambda x: x[1], reverse=True)
    if len(s10) > 2:
        b_tm = s10[:-2]
        d_tm = s10[-2:]
    else:
        b_tm = s10
        d_tm = []
    bm_tm = round(sum(p[1] for p in b_tm) / len(b_tm), 2) if b_tm else 0.0
    ty_tm = round(bm_tm * il_val, 2)

    if active_method == "3b5":
        bm = bm_3b5
        ty = ty_3b5
        active_selected = b3
        active_dropped = d5
        active_series = p5
        active_label = "3B5 (Best 3 of 5 Years)"
    elif active_method == "tm":
        bm = bm_tm
        ty = ty_tm
        active_selected = b_tm
        active_dropped = d_tm
        active_series = p10
        active_label = "TM (10 Years − 2 Worst Years)"
    else:
        active_method = "5b7"
        bm = bm_5b7
        ty = ty_5b7
        active_selected = b5
        active_dropped = d7
        active_series = p7
        active_label = "5B7 (Best 5 of 7 Years)"

    return {
        "active_method": active_method,
        "method_label": active_label,
        "benchmark_yield": bm,
        "threshold_yield": ty,
        "selected_yields": active_selected,
        "dropped_yields": active_dropped,
        "active_series": active_series,
        "methods": {
            "5b7": {"benchmark": bm_5b7, "ty": ty_5b7, "selected": [p[0] for p in b5], "dropped": [p[0] for p in d7]},
            "3b5": {"benchmark": bm_3b5, "ty": ty_3b5, "selected": [p[0] for p in b3], "dropped": [p[0] for p in d5]},
            "tm":  {"benchmark": bm_tm,  "ty": ty_tm,  "selected": [p[0] for p in b_tm], "dropped": [p[0] for p in d_tm]}
        }
    }

class ExcelReviewService:
    @staticmethod
    def _build_crop_wise(ty_rows: List[Dict[str, Any]], default_il: float) -> List[Dict[str, Any]]:
        crop_groups: Dict[str, List[Dict[str, Any]]] = {}
        for r in ty_rows:
            c = r.get("crop") or "General Crop"
            if c not in crop_groups:
                crop_groups[c] = []
            crop_groups[c].append(r)

        crop_wise = []
        for c_name, grp in crop_groups.items():
            cnt = len(grp)
            si_ha_list = [r["sum_insured_ha"] for r in grp if r.get("sum_insured_ha")]
            avg_si = round(sum(si_ha_list) / len(si_ha_list), 2) if si_ha_list else 0.0
            
            si_tot_list = [r["total_sum_insured_row"] for r in grp if r.get("total_sum_insured_row")]
            tot_si = round(sum(si_tot_list), 2) if si_tot_list else round(sum(si_ha_list), 2)
            
            avg_bm = round(sum(r["benchmark_yield"] for r in grp) / cnt, 2)
            avg_ty_val = round(sum(r["threshold_yield"] for r in grp) / cnt, 2)

            bm_5b7_crop = round(sum(r["methods"]["5b7"]["benchmark"] for r in grp) / cnt, 2)
            ty_5b7_crop = round(sum(r["methods"]["5b7"]["ty"] for r in grp) / cnt, 2)
            bm_3b5_crop = round(sum(r["methods"]["3b5"]["benchmark"] for r in grp) / cnt, 2)
            ty_3b5_crop = round(sum(r["methods"]["3b5"]["ty"] for r in grp) / cnt, 2)
            bm_tm_crop  = round(sum(r["methods"]["tm"]["benchmark"] for r in grp) / cnt, 2)
            ty_tm_crop  = round(sum(r["methods"]["tm"]["ty"] for r in grp) / cnt, 2)
            
            act_vals = [r["actual_season_yield"] for r in grp if r.get("actual_season_yield") is not None]
            avg_act = round(sum(act_vals) / len(act_vals), 2) if act_vals else None
            
            sf_vals = [r["shortfall_pct"] for r in grp if r.get("shortfall_pct") is not None]
            avg_sf_val = round(sum(sf_vals) / len(sf_vals), 2) if sf_vals else 0.0
            
            claims_in_crop = [r for r in grp if r.get("has_claim")]
            claim_freq_val = round(len(claims_in_crop) / cnt * 100.0, 1) if cnt > 0 else 0.0
            
            payout_vals = [r["claim_payout_ha"] for r in grp if r.get("claim_payout_ha")]
            avg_payout = round(sum(payout_vals) / cnt, 2) if cnt > 0 else 0.0
            tot_payout = round(sum(payout_vals), 2)

            avg_bc = round(sum(r.get("burning_cost_pct", 0.0) for r in grp) / cnt, 2) if cnt > 0 else 0.0

            crop_wise.append({
                "crop": c_name,
                "notified_units": cnt,
                "burning_cost_pct": avg_bc,
                "districts_covered": len(set(r.get("district") for r in grp if r.get("district"))),
                "avg_sum_insured_ha": avg_si,
                "total_sum_insured_ha": tot_si,
                "total_sum_insured_crore": round(tot_si / 10000000.0, 2),
                "avg_benchmark_yield_kg_ha": avg_bm,
                "indemnity_level_pct": round(default_il * 100.0, 1),
                "avg_threshold_yield_kg_ha": avg_ty_val,
                "avg_actual_yield_kg_ha": avg_act,
                "avg_shortfall_pct": avg_sf_val,
                "claim_units": len(claims_in_crop),
                "claim_frequency_pct": claim_freq_val,
                "avg_claim_payout_ha": avg_payout,
                "total_claim_payout_ha": tot_payout,
                "methods": {
                    "5b7": {"benchmark": bm_5b7_crop, "ty": ty_5b7_crop},
                    "3b5": {"benchmark": bm_3b5_crop, "ty": ty_3b5_crop},
                    "tm":  {"benchmark": bm_tm_crop,  "ty": ty_tm_crop}
                }
            })
        crop_wise.sort(key=lambda x: x["total_sum_insured_ha"], reverse=True)
        return crop_wise

    @staticmethod
    def _build_cluster_wise(ty_rows: List[Dict[str, Any]], default_il: float) -> List[Dict[str, Any]]:
        cluster_groups: Dict[str, List[Dict[str, Any]]] = {}
        for r in ty_rows:
            cl = r.get("cluster") or "General Cluster"
            if cl not in cluster_groups:
                cluster_groups[cl] = []
            cluster_groups[cl].append(r)

        cluster_wise = []
        for cl_name, grp in cluster_groups.items():
            cnt = len(grp)
            st = grp[0].get("state", "") if grp else ""
            crops_in_cluster = sorted(list(set(r.get("crop") for r in grp if r.get("crop"))))
            
            si_ha_list = [r["sum_insured_ha"] for r in grp if r.get("sum_insured_ha")]
            avg_si = round(sum(si_ha_list) / len(si_ha_list), 2) if si_ha_list else 0.0
            
            si_tot_list = [r["total_sum_insured_row"] for r in grp if r.get("total_sum_insured_row")]
            tot_si = round(sum(si_tot_list), 2) if si_tot_list else round(sum(si_ha_list), 2)
            
            avg_bm = round(sum(r["benchmark_yield"] for r in grp) / cnt, 2)
            avg_ty_val = round(sum(r["threshold_yield"] for r in grp) / cnt, 2)

            bm_5b7_cl = round(sum(r["methods"]["5b7"]["benchmark"] for r in grp) / cnt, 2)
            ty_5b7_cl = round(sum(r["methods"]["5b7"]["ty"] for r in grp) / cnt, 2)
            bm_3b5_cl = round(sum(r["methods"]["3b5"]["benchmark"] for r in grp) / cnt, 2)
            ty_3b5_cl = round(sum(r["methods"]["3b5"]["ty"] for r in grp) / cnt, 2)
            bm_tm_cl  = round(sum(r["methods"]["tm"]["benchmark"] for r in grp) / cnt, 2)
            ty_tm_cl  = round(sum(r["methods"]["tm"]["ty"] for r in grp) / cnt, 2)
            
            sf_vals = [r["shortfall_pct"] for r in grp if r.get("shortfall_pct") is not None]
            avg_sf_val = round(sum(sf_vals) / len(sf_vals), 2) if sf_vals else 0.0
            
            claims_in_cl = [r for r in grp if r.get("has_claim")]
            claim_freq_val = round(len(claims_in_cl) / cnt * 100.0, 1) if cnt > 0 else 0.0
            
            payout_vals = [r["claim_payout_ha"] for r in grp if r.get("claim_payout_ha")]
            avg_payout = round(sum(payout_vals) / cnt, 2) if cnt > 0 else 0.0
            tot_payout = round(sum(payout_vals), 2)

            si_weights = [r.get("total_sum_insured_row") or r.get("sum_insured_ha") or 1.0 for r in grp]
            tot_weights = sum(si_weights)
            if tot_weights > 0:
                cluster_bc = round(sum(r.get("burning_cost_pct", 0.0) * w for r, w in zip(grp, si_weights)) / tot_weights, 2)
            else:
                cluster_bc = round(sum(r.get("burning_cost_pct", 0.0) for r in grp) / cnt, 2) if cnt > 0 else 0.0

            cat_loading = 10.0  # Default 10% CAT loading
            other_loading = 12.0  # Default 12% Other loading
            cat_amt = round(cluster_bc * (cat_loading / 100.0), 2)
            other_amt = round(cluster_bc * (other_loading / 100.0), 2)
            appr_val = round(cluster_bc + cat_amt + other_amt, 2)
            quoted_prem = round(appr_val * 1.15, 2) if appr_val > 0 else 12.0
            lr_val = round((appr_val / quoted_prem * 100.0), 2) if quoted_prem > 0 else 0.0

            cluster_wise.append({
                "cluster": cl_name,
                "state": st,
                "crops_count": len(crops_in_cluster),
                "crops_list": ", ".join(crops_in_cluster),
                "total_notified_units": cnt,
                "burning_cost_pct": cluster_bc,
                "cat_loading_pct": cat_loading,
                "other_loading_pct": other_loading,
                "cat_loading_amount": cat_amt,
                "other_loading_amount": other_amt,
                "appr_pct": appr_val,
                "quoted_premium_rate_pct": quoted_prem,
                "expected_loss_ratio_pct": lr_val,
                "plr_pct": lr_val,
                "avg_sum_insured_ha": avg_si,
                "total_sum_insured_ha": tot_si,
                "total_sum_insured_crore": round(tot_si / 10000000.0, 2),
                "avg_benchmark_yield_kg_ha": avg_bm,
                "indemnity_level_pct": round(default_il * 100.0, 1),
                "avg_threshold_yield_kg_ha": avg_ty_val,
                "avg_shortfall_pct": avg_sf_val,
                "claim_units": len(claims_in_cl),
                "claim_frequency_pct": claim_freq_val,
                "avg_claim_payout_ha": avg_payout,
                "total_claim_payout_ha": tot_payout,
                "methods": {
                    "5b7": {"benchmark": bm_5b7_cl, "ty": ty_5b7_cl},
                    "3b5": {"benchmark": bm_3b5_cl, "ty": ty_3b5_cl},
                    "tm":  {"benchmark": bm_tm_cl,  "ty": ty_tm_cl}
                }
            })
        cluster_wise.sort(key=lambda x: x["total_sum_insured_ha"], reverse=True)
        return cluster_wise

    @classmethod
    def _build_state_wise(cls, ty_rows: List[Dict[str, Any]], default_il: float) -> Dict[str, Any]:
        state_groups: Dict[str, List[Dict[str, Any]]] = {}
        for r in ty_rows:
            raw_st = str(r.get("state") or "").strip()
            st = raw_st.upper() if raw_st and raw_st.lower() != "none" else "OTHER / GENERAL"
            if st not in state_groups:
                state_groups[st] = []
            state_groups[st].append(r)

        state_wise = {}
        for st_name, s_rows in state_groups.items():
            s_cnt = len(s_rows)
            si_ha = [r["sum_insured_ha"] for r in s_rows if r.get("sum_insured_ha")]
            si_tot = [r["total_sum_insured_row"] for r in s_rows if r.get("total_sum_insured_row")]
            tot_si = round(sum(si_tot), 2) if si_tot else round(sum(si_ha), 2)
            avg_si = round(sum(si_ha) / len(si_ha), 2) if si_ha else 0.0

            s_bm = round(sum(r["benchmark_yield"] for r in s_rows) / s_cnt, 2)
            s_ty = round(sum(r["threshold_yield"] for r in s_rows) / s_cnt, 2)

            s_bm_5b7 = round(sum(r["methods"]["5b7"]["benchmark"] for r in s_rows) / s_cnt, 2)
            s_ty_5b7 = round(sum(r["methods"]["5b7"]["ty"] for r in s_rows) / s_cnt, 2)
            s_bm_3b5 = round(sum(r["methods"]["3b5"]["benchmark"] for r in s_rows) / s_cnt, 2)
            s_ty_3b5 = round(sum(r["methods"]["3b5"]["ty"] for r in s_rows) / s_cnt, 2)
            s_bm_tm  = round(sum(r["methods"]["tm"]["benchmark"] for r in s_rows) / s_cnt, 2)
            s_ty_tm  = round(sum(r["methods"]["tm"]["ty"] for r in s_rows) / s_cnt, 2)

            if tot_si > 10000000:
                s_display = f"₹{round(tot_si / 10000000.0, 2):,.2f} Cr"
            elif tot_si > 0:
                s_display = f"₹{tot_si:,.2f}"
            else:
                s_display = "₹0.00"

            s_bc = round(sum(r.get("burning_cost_pct", 0.0) for r in s_rows) / s_cnt, 2) if s_cnt > 0 else 0.0

            state_wise[st_name] = {
                "state": st_name,
                "total_units": s_cnt,
                "burning_cost_pct": s_bc,
                "total_sum_insured": tot_si,
                "total_sum_insured_crore": round(tot_si / 10000000.0, 2),
                "total_sum_insured_display": s_display,
                "avg_sum_insured_ha": avg_si,
                "avg_benchmark_yield_kg_ha": s_bm,
                "avg_threshold_yield_kg_ha": s_ty,
                "methods": {
                    "5b7": {"benchmark": s_bm_5b7, "ty": s_ty_5b7},
                    "3b5": {"benchmark": s_bm_3b5, "ty": s_ty_3b5},
                    "tm":  {"benchmark": s_bm_tm,  "ty": s_ty_tm}
                },
                "crop_wise_analysis": cls._build_crop_wise(s_rows, default_il),
                "cluster_wise_analysis": cls._build_cluster_wise(s_rows, default_il),
                "rows": s_rows[:150]
            }
        return state_wise

    @staticmethod
    def inspect_and_review(
        file_bytes: bytes, 
        filename: str, 
        selected_sheet: Optional[str] = None, 
        indemnity_override: Optional[float] = None,
        ty_method: Optional[str] = "5b7"
    ) -> Dict[str, Any]:
        """Loads workbook, parses active sheet, and produces actuarial review and threshold yield calculation."""
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        sheet_names = wb.sheetnames

        if not selected_sheet or selected_sheet not in sheet_names:
            # Smart sheet selection: prioritize sheets with yield, cce, kharif, tender, best_5
            preferred = [s for s in sheet_names if any(k in s.lower() for k in ["threshold", "yield", "cce", "best_5", "kharif"])]
            active_sheet_name = preferred[0] if preferred else sheet_names[0]
        else:
            active_sheet_name = selected_sheet

        ws = wb[active_sheet_name]

        raw_rows = list(ws.iter_rows(values_only=True))
        if not raw_rows:
            return {
                "filename": filename,
                "sheet_names": sheet_names,
                "active_sheet": active_sheet_name,
                "total_rows": 0,
                "error": "The selected sheet is empty."
            }

        header_idx = find_header_row(raw_rows)
        raw_headers = raw_rows[header_idx]
        headers = []
        for i, h in enumerate(raw_headers):
            val = str(h).strip() if h is not None else ""
            if not val:
                val = f"Col_{i+1}"
            headers.append(val)

        col_map = identify_columns(headers)
        yield_col_indices = identify_yield_series_columns(headers)

        parsed_rows = []
        tot_prem = 0.0
        tot_claims = 0.0
        tot_sum_insured = 0.0
        si_count = 0
        sum_lr = 0.0
        count_lr = 0
        aprs_list = []
        anomalies = []

        # Threshold Yield Collection
        ty_rows = []
        default_il = indemnity_override if indemnity_override is not None else 0.80
        active_method = (ty_method or "5b7").strip().lower()

        data_rows = raw_rows[header_idx + 1:]
        for r_idx, row in enumerate(data_rows):
            if all(c is None for c in row):
                continue

            row_dict = {}
            for c_idx, val in enumerate(row):
                if c_idx < len(headers):
                    row_dict[headers[c_idx]] = val

            # Extract metrics
            prem_val = clean_float(row[col_map["premium"]]) if col_map["premium"] is not None and col_map["premium"] < len(row) else None
            claims_val = clean_float(row[col_map["claims"]]) if col_map["claims"] is not None and col_map["claims"] < len(row) else None
            lr_val = clean_float(row[col_map["loss_ratio"]]) if col_map["loss_ratio"] is not None and col_map["loss_ratio"] < len(row) else None
            apr_val = clean_float(row[col_map["apr"]]) if col_map["apr"] is not None and col_map["apr"] < len(row) else None
            entity_val = str(row[col_map["entity"]]).strip() if col_map["entity"] is not None and col_map["entity"] < len(row) and row[col_map["entity"]] is not None else f"Row {r_idx+1}"

            # Skip summary rows (e.g. Total, National Total)
            if any(k in entity_val.lower() for k in ["total", "summary", "overall", "aggregate"]):
                continue

            if prem_val is not None and prem_val > 0:
                tot_prem += prem_val
            if claims_val is not None and claims_val >= 0:
                tot_claims += claims_val

            # Sum Insured Extraction (Total and Per Hectare)
            si_tot_val = clean_float(row[col_map["sum_insured_total"]]) if col_map.get("sum_insured_total") is not None and col_map["sum_insured_total"] < len(row) else None
            si_ha_val = clean_float(row[col_map["si_per_ha"]]) if col_map.get("si_per_ha") is not None and col_map["si_per_ha"] < len(row) else None
            if si_tot_val is None and col_map.get("sum_insured") is not None and col_map["sum_insured"] < len(row):
                si_tot_val = clean_float(row[col_map["sum_insured"]])

            if si_tot_val is not None and si_tot_val > 0:
                tot_sum_insured += si_tot_val
                si_count += 1
            elif si_ha_val is not None and si_ha_val > 0:
                tot_sum_insured += si_ha_val
                si_count += 1

            # Compute row loss ratio
            if lr_val is None and prem_val is not None and prem_val > 0 and claims_val is not None:
                lr_val = round((claims_val / prem_val) * 100.0, 2)

            if lr_val is not None:
                sum_lr += lr_val
                count_lr += 1

            if apr_val is not None and apr_val > 0:
                aprs_list.append(apr_val)

            # Check Anomalies
            if apr_val is not None and apr_val > 30.0:
                anomalies.append({
                    "entity": entity_val,
                    "type": "GoI Capping Violation",
                    "severity": "High",
                    "detail": f"Quoted APR of {apr_val:.2f}% exceeds the 30% GoI central subsidy eligible ceiling."
                })
            if lr_val is not None and lr_val > 100.0:
                anomalies.append({
                    "entity": entity_val,
                    "type": "Deficit Underwriting",
                    "severity": "Warning",
                    "detail": f"Incurred claims exceed gross premium (Loss Ratio: {lr_val:.1f}%)."
                })
            elif lr_val is not None and lr_val < 30.0 and (prem_val or 0) > 50:
                anomalies.append({
                    "entity": entity_val,
                    "type": "Excessive Margin",
                    "severity": "Info",
                    "detail": f"Very low Loss Ratio ({lr_val:.1f}%) on high volume premium (₹{prem_val:,.1f} Cr); potential clawback candidate under Beed formula."
                })

            # ----------------------------------------------------
            # THRESHOLD YIELD (TY) THREE-METHOD CALCULATION (3B5, 5B7, TM)
            # ----------------------------------------------------
            if len(yield_col_indices) >= 3:
                # Gather historical yields in chronological order
                yield_pairs: List[Tuple[str, float]] = []
                for y_idx in yield_col_indices:
                    if y_idx < len(row):
                        y_val = clean_float(row[y_idx])
                        if y_val is not None and y_val > 0:
                            yield_pairs.append((headers[y_idx], y_val))

                if len(yield_pairs) >= 3:
                    # Determine Indemnity Level
                    il_val = default_il
                    if indemnity_override is not None:
                        il_val = indemnity_override
                    elif col_map["indemnity"] is not None and col_map["indemnity"] < len(row):
                        extracted_il = clean_float(row[col_map["indemnity"]])
                        if extracted_il:
                            il_val = extracted_il / 100.0 if extracted_il > 1.0 else extracted_il

                    # Compute all 3 methodologies (3B5, 5B7, TM)
                    ty_eval = compute_ty_methods(yield_pairs, il_val, active_method)
                    threshold_yield = ty_eval["threshold_yield"]
                    benchmark_yield = ty_eval["benchmark_yield"]

                    # Actual Yield & Shortfall
                    act_y = clean_float(row[col_map["actual_yield"]]) if col_map["actual_yield"] is not None and col_map["actual_yield"] < len(row) else None
                    row_display_si = si_ha_val if (si_ha_val is not None and si_ha_val > 0) else si_tot_val

                    if act_y is not None:
                        shortfall = max(0.0, threshold_yield - act_y)
                        shortfall_pct = round((shortfall / threshold_yield * 100.0), 2) if threshold_yield > 0 else 0.0
                        claim_payout = round((shortfall_pct / 100.0) * row_display_si, 2) if row_display_si else None
                    else:
                        shortfall = None
                        shortfall_pct = None
                        claim_payout = None

                    # Extract identifying info with dynamic column map
                    state_name = str(row[col_map["state"]]).strip() if (col_map["state"] is not None and col_map["state"] < len(row) and row[col_map["state"]] is not None) else (str(row[0]).strip() if len(row) > 0 and row[0] is not None else "")
                    raw_cluster = row[col_map["cluster"]] if (col_map["cluster"] is not None and col_map["cluster"] < len(row)) else None
                    if raw_cluster is not None and str(raw_cluster).strip():
                        c_str = str(raw_cluster).strip()
                        cluster_name = f"Cluster {c_str}" if c_str.isdigit() else c_str
                    else:
                        cluster_name = ""

                    dist_name = str(row[col_map["district"]]).strip() if (col_map["district"] is not None and col_map["district"] < len(row) and row[col_map["district"]] is not None) else (str(row[1]).strip() if len(row) > 1 and row[1] is not None else "")
                    crop_name = str(row[col_map["crop"]]).strip() if (col_map["crop"] is not None and col_map["crop"] < len(row) and row[col_map["crop"]] is not None) else (str(row[2]).strip() if len(row) > 2 and row[2] is not None else "General Crop")
                    season_name = str(row[col_map["season"]]).strip() if (col_map["season"] is not None and col_map["season"] < len(row) and row[col_map["season"]] is not None) else (str(row[3]).strip() if len(row) > 3 and row[3] is not None else "Kharif")

                    if not cluster_name:
                        cluster_name = f"Cluster ({dist_name})" if dist_name else (f"Cluster ({state_name})" if state_name else "Cluster 1 (Default)")

                    yearly_payouts = []
                    for yp in yield_pairs:
                        yr, y_val = yp[0], yp[1]
                        if y_val is not None and threshold_yield > 0:
                            sf = max(0.0, threshold_yield - y_val)
                            var_pct = round((sf / threshold_yield) * 100.0, 2)
                        else:
                            sf = 0.0
                            var_pct = 0.0
                        payout_inr = round((var_pct / 100.0) * row_display_si, 2) if row_display_si else 0.0
                        yearly_payouts.append({
                            "year": str(yr),
                            "yield": y_val,
                            "shortfall": round(sf, 2),
                            "variation_pct": var_pct,
                            "payout_pct": var_pct,
                            "payout_inr": payout_inr,
                            "has_payout": var_pct > 0
                        })

                    row_bc_pct = round(sum(p["payout_pct"] for p in yearly_payouts) / len(yearly_payouts), 2) if yearly_payouts else 0.0

                    ty_rows.append({
                        "yearly_payouts": yearly_payouts,
                        "burning_cost_pct": row_bc_pct,
                        "entity": entity_val,
                        "cluster": cluster_name,
                        "state": state_name,
                        "district": dist_name,
                        "crop": crop_name,
                        "season": season_name,
                        "active_method": ty_eval["active_method"],
                        "active_method_label": ty_eval["method_label"],
                        "historical_yields": [{"year": p[0], "yield": p[1], "is_best_5": p in ty_eval["selected_yields"], "is_best": p in ty_eval["selected_yields"]} for p in ty_eval["active_series"]],
                        "best_5_yields": [{"year": p[0], "yield": p[1]} for p in ty_eval["selected_yields"]],
                        "dropped_yields": [{"year": p[0], "yield": p[1]} for p in ty_eval["dropped_yields"]],
                        "benchmark_yield": benchmark_yield,
                        "benchmark_yield_best_5": benchmark_yield, # backward compatibility
                        "indemnity_level_pct": round(il_val * 100.0, 1),
                        "threshold_yield": threshold_yield,
                        "actual_season_yield": act_y,
                        "shortfall_pct": shortfall_pct,
                        "sum_insured_ha": row_display_si,
                        "total_sum_insured_row": si_tot_val,
                        "claim_payout_ha": claim_payout,
                        "has_claim": shortfall_pct is not None and shortfall_pct > 0,
                        "methods": ty_eval["methods"],
                        "all_yields_series": [{"year": p[0], "yield": p[1]} for p in yield_pairs]
                    })

            parsed_rows.append(row_dict)

        # Aggregate portfolio calculations
        overall_lr = round((tot_claims / tot_prem * 100.0), 2) if tot_prem > 0 else (round(sum_lr / count_lr, 2) if count_lr > 0 else 0.0)

        # Pricing Adequacy Verdict
        if overall_lr > 100.0:
            verdict = "Severe Loss / Underpriced Portfolio"
            verdict_badge = "badge-loss"
            verdict_desc = "Aggregate incurred claims exceed total premium. The pricing is inadequate or the season suffered severe catastrophic losses."
        elif overall_lr > 75.0:
            verdict = "Marginal Risk / Elevated Loss"
            verdict_badge = "badge-marginal"
            verdict_desc = "Loss ratio is above 75%. After operational expenses (~15%), insurer margins are constrained or break-even."
        elif overall_lr >= 50.0:
            verdict = "Technically Sound / Healthy Margin"
            verdict_badge = "badge-healthy"
            verdict_desc = "Optimal actuarial corridor: Sufficient loss absorption capacity with sustainable underwriting margin."
        else:
            verdict = "Highly Profitable / Conservative Pricing"
            verdict_badge = "badge-profitable"
            verdict_desc = "Substantial underwriting surplus. Subject to significant refund under Beed 80:110 profit-sharing clauses."

        # Simulate Beed 80:110 on this uploaded portfolio
        lower_80 = 0.80 * tot_prem
        upper_110 = 1.10 * tot_prem

        if tot_claims < lower_80:
            refund_to_govt = lower_80 - tot_claims
            govt_tail = 0.0
            insurer_claims_paid = tot_claims
            insurer_retention = 0.20 * tot_prem
            beed_status = "Below 80%: State Treasury Clawback / Refund Zone"
        elif tot_claims <= upper_110:
            refund_to_govt = 0.0
            govt_tail = 0.0
            insurer_claims_paid = tot_claims
            insurer_retention = tot_prem - tot_claims
            beed_status = "80% - 110%: Normal Insurer Risk Retention Corridor"
        else:
            refund_to_govt = 0.0
            govt_tail = tot_claims - upper_110
            insurer_claims_paid = upper_110
            insurer_retention = -0.10 * tot_prem
            beed_status = "Above 110%: Government Fiscal Subvention / Tail-Risk Zone"

        avg_apr = round(sum(aprs_list) / len(aprs_list), 2) if aprs_list else None

        # Build Threshold Yield Analysis if rows present
        threshold_analysis = None
        if ty_rows:
            avg_benchmark = round(sum(r["benchmark_yield"] for r in ty_rows) / len(ty_rows), 2)
            avg_ty = round(sum(r["threshold_yield"] for r in ty_rows) / len(ty_rows), 2)
            
            # Method-level summary across entire portfolio
            avg_bm_5b7 = round(sum(r["methods"]["5b7"]["benchmark"] for r in ty_rows) / len(ty_rows), 2)
            avg_ty_5b7 = round(sum(r["methods"]["5b7"]["ty"] for r in ty_rows) / len(ty_rows), 2)
            avg_bm_3b5 = round(sum(r["methods"]["3b5"]["benchmark"] for r in ty_rows) / len(ty_rows), 2)
            avg_ty_3b5 = round(sum(r["methods"]["3b5"]["ty"] for r in ty_rows) / len(ty_rows), 2)
            avg_bm_tm  = round(sum(r["methods"]["tm"]["benchmark"] for r in ty_rows) / len(ty_rows), 2)
            avg_ty_tm  = round(sum(r["methods"]["tm"]["ty"] for r in ty_rows) / len(ty_rows), 2)

            valid_sf = [r["shortfall_pct"] for r in ty_rows if r["shortfall_pct"] is not None]
            avg_sf = round(sum(valid_sf) / len(valid_sf), 2) if valid_sf else 0.0

            valid_payout = [r["claim_payout_ha"] for r in ty_rows if r["claim_payout_ha"] is not None]
            total_claim_ha = round(sum(valid_payout), 2) if valid_payout else 0.0

            claim_units = sum(1 for r in ty_rows if r["has_claim"])

            # Modular Aggregations across Crops, Clusters, and States
            crop_wise = ExcelReviewService._build_crop_wise(ty_rows, default_il)
            cluster_wise = ExcelReviewService._build_cluster_wise(ty_rows, default_il)
            state_wise = ExcelReviewService._build_state_wise(ty_rows, default_il)
            states_list = sorted(list(state_wise.keys()))

            active_label = (
                "3B5 (Best 3 of 5 Years)" if active_method == "3b5" else
                ("TM (10 Years − 2 Worst Years)" if active_method == "tm" else "5B7 (Best 5 of 7 Years)")
            )

            portfolio_bc = round(sum(r.get("burning_cost_pct", 0.0) for r in ty_rows) / len(ty_rows), 2) if ty_rows else 0.0

            threshold_analysis = {
                "has_yield_data": True,
                "portfolio_burning_cost_pct": portfolio_bc,
                "all_rows": ty_rows,
                "active_method": active_method,
                "active_method_label": active_label,
                "available_methods": [
                    {"id": "3b5", "name": "3B5", "label": "Best 3 of 5 Years", "description": "Average of best 3 yields out of preceding 5 years × Indemnity"},
                    {"id": "5b7", "name": "5B7", "label": "Best 5 of 7 Years (Standard PMFBY)", "description": "Average of best 5 yields out of preceding 7 years × Indemnity"},
                    {"id": "tm",  "name": "TM",  "label": "10 Years − 2 Worst Years (Trimmed Mean)", "description": "Last 10 years yield minus 2 worst years (8-year trimmed mean) × Indemnity"}
                ],
                "methods_summary": {
                    "5b7": {"avg_benchmark": avg_bm_5b7, "avg_ty": avg_ty_5b7},
                    "3b5": {"avg_benchmark": avg_bm_3b5, "avg_ty": avg_ty_3b5},
                    "tm":  {"avg_benchmark": avg_bm_tm,  "avg_ty": avg_ty_tm}
                },
                "total_units": len(ty_rows),
                "yield_years_detected": [headers[i] for i in yield_col_indices],
                "active_indemnity_pct": round(default_il * 100.0, 1),
                "avg_benchmark_yield_kg_ha": avg_benchmark,
                "avg_threshold_yield_kg_ha": avg_ty,
                "avg_shortfall_pct": avg_sf,
                "claim_triggering_units": claim_units,
                "claim_frequency_pct": round((claim_units / len(ty_rows) * 100.0), 1),
                "total_estimated_payout_ha": total_claim_ha,
                "crop_wise_analysis": crop_wise,
                "cluster_wise_analysis": cluster_wise,
                "states_list": states_list,
                "state_wise_analysis": state_wise,
                "rows": ty_rows[:150]
            }

        # Sum Insured Formatting
        if tot_sum_insured > 10000000:
            total_si_crore = round(tot_sum_insured / 10000000.0, 2)
            sum_insured_display = f"₹{total_si_crore:,.2f} Cr"
            si_sub_label = f"Aggregated Portfolio Sum Insured ({len(parsed_rows):,} Records)"
        elif tot_sum_insured > 0:
            total_si_crore = round(tot_sum_insured, 2)
            sum_insured_display = f"₹{tot_sum_insured:,.2f}"
            si_sub_label = f"Aggregated Sum Insured ({si_count:,} Items)"
        else:
            total_si_crore = 0.0
            sum_insured_display = "₹0.0 Cr"
            si_sub_label = "No Sum Insured column detected"

        review_summary = {
            "total_sum_insured": round(tot_sum_insured, 2),
            "total_sum_insured_crore": total_si_crore,
            "total_sum_insured_display": sum_insured_display,
            "total_sum_insured_sub_label": si_sub_label,
            "avg_sum_insured_ha": round(tot_sum_insured / si_count, 2) if si_count > 0 else 0.0,
            "total_gross_premium_crore": round(tot_prem, 2),
            "total_claims_paid_crore": round(tot_claims, 2),
            "portfolio_loss_ratio_pct": overall_lr,
            "avg_actuarial_rate_pct": avg_apr,
            "pricing_verdict": verdict,
            "verdict_badge": verdict_badge,
            "verdict_desc": verdict_desc
        }

        return {
            "filename": filename,
            "sheet_names": sheet_names,
            "active_sheet": active_sheet_name,
            "total_rows": len(parsed_rows),
            "is_multi_file": False,
            "states_list": states_list if threshold_analysis else [],
            "state_wise_analysis": state_wise if threshold_analysis else {},
            "headers": headers,
            "column_mapping": {k: headers[v] if v is not None and v < len(headers) else None for k, v in col_map.items()},
            "summary": review_summary,
            "beed_simulation": {
                "gross_premium_crore": round(tot_prem, 2),
                "actual_claims_paid_crore": round(tot_claims, 2),
                "actual_loss_ratio_pct": overall_lr,
                "refund_to_govt_crore": round(refund_to_govt, 2),
                "insurer_claims_paid_crore": round(insurer_claims_paid, 2),
                "govt_tail_liability_crore": round(govt_tail, 2),
                "insurer_net_retention_crore": round(insurer_retention, 2),
                "net_fiscal_benefit_crore": round(refund_to_govt - govt_tail, 2),
                "beed_status": beed_status
            },
            "threshold_yield_analysis": threshold_analysis,
            "anomalies": anomalies[:15],
            "sample_rows": parsed_rows[:150]
        }

    @classmethod
    def inspect_and_review_multiple(
        cls,
        file_items: List[Tuple[bytes, str]],
        selected_sheet: Optional[str] = None,
        indemnity_override: Optional[float] = None,
        ty_method: Optional[str] = "5b7"
    ) -> Dict[str, Any]:
        """Merges multiple uploaded Excel workbooks, standardizes states, and computes multi-state actuarial analytics."""
        if not file_items:
            raise ValueError("No files provided for multi-file review.")

        reviews: List[Dict[str, Any]] = []
        all_ty_rows: List[Dict[str, Any]] = []
        all_parsed_rows: List[Dict[str, Any]] = []
        all_anomalies: List[Dict[str, Any]] = []
        uploaded_filenames: List[str] = []
        total_sum_insured_all = 0.0

        for f_bytes, f_name in file_items:
            uploaded_filenames.append(f_name)
            rev = cls.inspect_and_review(
                f_bytes, 
                f_name, 
                selected_sheet=selected_sheet, 
                indemnity_override=indemnity_override, 
                ty_method=ty_method
            )
            reviews.append(rev)
            
            # Infer clean state name from filename if rows have missing/blank state
            inferred_state = f_name.rsplit('.', 1)[0].replace('_', ' ').replace('-', ' ').upper()
            # Clean common words like PMFBY, PRICING, CCE, REVIEW, 2024, 2025, 2026
            for cw in ["PMFBY", "PRICING", "REVIEW", "CCE", "TENDER", "DATA", "FINAL", "2024", "2025", "2026", "2023", "2022"]:
                inferred_state = inferred_state.replace(cw, "").strip()
            if not inferred_state:
                inferred_state = "PORTFOLIO FILE"

            if rev.get("threshold_yield_analysis") and rev["threshold_yield_analysis"].get("rows"):
                t_rows = rev["threshold_yield_analysis"].get("all_rows") or rev["threshold_yield_analysis"]["rows"]
                for r in t_rows:
                    if not r.get("state") or str(r.get("state")).strip().lower() in ["none", ""]:
                        r["state"] = inferred_state
                    r["source_file"] = f_name
                    all_ty_rows.append(r)

            if rev.get("sample_rows"):
                all_parsed_rows.extend(rev["sample_rows"])
            if rev.get("anomalies"):
                all_anomalies.extend(rev["anomalies"])
            if rev.get("summary"):
                total_sum_insured_all += rev["summary"].get("total_sum_insured", 0.0)

        # Build consolidated metrics across all uploaded files
        default_il = indemnity_override if indemnity_override is not None else 0.80
        crop_wise = cls._build_crop_wise(all_ty_rows, default_il)
        cluster_wise = cls._build_cluster_wise(all_ty_rows, default_il)
        state_wise = cls._build_state_wise(all_ty_rows, default_il)
        states_list = sorted(list(state_wise.keys()))

        # Consolidate Threshold Analysis
        first_ty = reviews[0].get("threshold_yield_analysis") or {}
        active_method = ty_method or "5b7"
        active_label = (
            "3B5 (Best 3 of 5 Years)" if active_method == "3b5" else
            ("TM (10 Years − 2 Worst Years)" if active_method == "tm" else "5B7 (Best 5 of 7 Years)")
        )

        avg_bm = round(sum(r["benchmark_yield"] for r in all_ty_rows) / len(all_ty_rows), 2) if all_ty_rows else 0.0
        avg_ty = round(sum(r["threshold_yield"] for r in all_ty_rows) / len(all_ty_rows), 2) if all_ty_rows else 0.0

        avg_bm_5b7 = round(sum(r["methods"]["5b7"]["benchmark"] for r in all_ty_rows) / len(all_ty_rows), 2) if all_ty_rows else 0.0
        avg_ty_5b7 = round(sum(r["methods"]["5b7"]["ty"] for r in all_ty_rows) / len(all_ty_rows), 2) if all_ty_rows else 0.0
        avg_bm_3b5 = round(sum(r["methods"]["3b5"]["benchmark"] for r in all_ty_rows) / len(all_ty_rows), 2) if all_ty_rows else 0.0
        avg_ty_3b5 = round(sum(r["methods"]["3b5"]["ty"] for r in all_ty_rows) / len(all_ty_rows), 2) if all_ty_rows else 0.0
        avg_bm_tm  = round(sum(r["methods"]["tm"]["benchmark"] for r in all_ty_rows) / len(all_ty_rows), 2) if all_ty_rows else 0.0
        avg_ty_tm  = round(sum(r["methods"]["tm"]["ty"] for r in all_ty_rows) / len(all_ty_rows), 2) if all_ty_rows else 0.0

        multi_portfolio_bc = round(sum(r.get("burning_cost_pct", 0.0) for r in all_ty_rows) / len(all_ty_rows), 2) if all_ty_rows else 0.0

        consolidated_ty_analysis = {
            "has_yield_data": len(all_ty_rows) > 0,
            "portfolio_burning_cost_pct": multi_portfolio_bc,
            "active_method": active_method,
            "active_method_label": active_label,
            "available_methods": first_ty.get("available_methods", [
                {"id": "3b5", "name": "3B5", "label": "Best 3 of 5 Years", "description": "Average of best 3 yields out of preceding 5 years × Indemnity"},
                {"id": "5b7", "name": "5B7", "label": "Best 5 of 7 Years (Standard PMFBY)", "description": "Average of best 5 yields out of preceding 7 years × Indemnity"},
                {"id": "tm",  "name": "TM",  "label": "10 Years − 2 Worst Years (Trimmed Mean)", "description": "Last 10 years yield minus 2 worst years (8-year trimmed mean) × Indemnity"}
            ]),
            "methods_summary": {
                "5b7": {"avg_benchmark": avg_bm_5b7, "avg_ty": avg_ty_5b7},
                "3b5": {"avg_benchmark": avg_bm_3b5, "avg_ty": avg_ty_3b5},
                "tm":  {"avg_benchmark": avg_bm_tm,  "avg_ty": avg_ty_tm}
            },
            "total_units": len(all_ty_rows),
            "yield_years_detected": first_ty.get("yield_years_detected", []),
            "active_indemnity_pct": round(default_il * 100.0, 1),
            "avg_benchmark_yield_kg_ha": avg_bm,
            "avg_threshold_yield_kg_ha": avg_ty,
            "avg_shortfall_pct": 0.0,
            "claim_triggering_units": sum(1 for r in all_ty_rows if r.get("has_claim")),
            "claim_frequency_pct": 0.0,
            "total_estimated_payout_ha": 0.0,
            "crop_wise_analysis": crop_wise,
            "cluster_wise_analysis": cluster_wise,
            "states_list": states_list,
            "state_wise_analysis": state_wise,
            "rows": all_ty_rows[:200]
        }

        # Sum Insured formatting
        if total_sum_insured_all > 10000000:
            si_display = f"₹{round(total_sum_insured_all / 10000000.0, 2):,.2f} Cr"
        elif total_sum_insured_all > 0:
            si_display = f"₹{total_sum_insured_all:,.2f}"
        else:
            si_display = "₹0.00"

        consolidated_summary = {
            "total_sum_insured": round(total_sum_insured_all, 2),
            "total_sum_insured_crore": round(total_sum_insured_all / 10000000.0, 2),
            "total_sum_insured_display": si_display,
            "total_sum_insured_sub_label": f"Consolidated across {len(file_items)} Workbooks ({len(all_ty_rows):,} Units)",
            "avg_sum_insured_ha": round(total_sum_insured_all / len(all_ty_rows), 2) if all_ty_rows else 0.0,
            "total_gross_premium_crore": 0.0,
            "total_claims_paid_crore": 0.0,
            "portfolio_loss_ratio_pct": 0.0,
            "avg_actuarial_rate_pct": 0.0,
            "pricing_verdict": f"Multi-File Consolidated Audit ({len(file_items)} Workbooks)",
            "verdict_badge": "badge-healthy",
            "verdict_desc": f"Consolidated analysis of {len(file_items)} files across {len(states_list)} states with {len(all_ty_rows):,} notified units."
        }

        first_rev = reviews[0]
        return {
            "filename": f"{len(file_items)} Workbooks Merged ({', '.join(uploaded_filenames[:2])}{'...' if len(uploaded_filenames) > 2 else ''})",
            "is_multi_file": True,
            "file_count": len(file_items),
            "uploaded_files": uploaded_filenames,
            "sheet_names": list(set(s for r in reviews for s in r.get("sheet_names", []))),
            "active_sheet": "Consolidated_Multi_State",
            "headers": first_rev.get("headers", []),
            "column_mapping": first_rev.get("column_mapping", {}),
            "total_rows": len(all_ty_rows) or len(all_parsed_rows),
            "states_list": states_list,
            "state_wise_analysis": state_wise,
            "sample_rows": all_parsed_rows[:50],
            "summary": consolidated_summary,
            "threshold_yield_analysis": consolidated_ty_analysis,
            "anomalies": all_anomalies[:50],
            "beed_simulation": first_rev.get("beed_simulation", {})
        }
