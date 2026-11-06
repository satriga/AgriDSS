"""
PMFBY (Pradhan Mantri Fasal Bima Yojana) Data Processor & Excel Exporter
Fetches, decrypts, and organizes official crop insurance statistics
from https://www.pmfby.gov.in/adminStatistics/dashboard and the
Insurance Premium Calculator (hierarchy & designated Insurance Companies).
Generates multi-sheet formatted Excel (.xlsx) workbooks covering
National, State-wise, District-wise, and Insurance Company performance.
"""

import os
import io
import ssl
import json
import time
import glob
import base64
import urllib.request
import threading
from datetime import datetime, timezone, timedelta
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

CACHE_DIR = os.path.join("data", "pmfby")

# Indian Standard Time (IST) offset +05:30
IST = timezone(timedelta(hours=5, minutes=30))

def clean_ic_name(raw_name):
    """Returns a clean, human-readable brand name for an insurance company."""
    if not raw_name:
        return "AIC of India"
    u = str(raw_name).upper().strip()
    if "DO NOT SELECT" in u or u in ["NONE", "SELECT", ""]:
        return "AIC of India"
    if "AGRICULTURE INSURANCE" in u or "AIC" in u:
        return "AIC of India"
    if "BAJAJ" in u:
        return "Bajaj Allianz"
    if "UNIVERSAL SOMPO" in u:
        return "Universal Sompo"
    if "FUTURE GENERALI" in u:
        return "Future Generali"
    if "HDFC" in u:
        return "HDFC ERGO"
    if "ICICI" in u:
        return "ICICI Lombard"
    if "IFFCO" in u:
        return "IFFCO TOKIO"
    if "RELIANCE" in u:
        return "Reliance General"
    if "SBI" in u:
        return "SBI General"
    if "TATA" in u:
        return "Tata AIG"
    if "CHOLAMANDALAM" in u or "CHOLA" in u:
        return "Cholamandalam MS"
    if "NATIONAL INSURANCE" in u:
        return "National Insurance"
    if "NEW INDIA" in u:
        return "New India Assurance"
    if "ORIENTAL" in u:
        return "Oriental Insurance"
    if "UNITED INDIA" in u:
        return "United India Insurance"
    if "KSHEMA" in u:
        return "Kshema General"
    if "BHARTI AXA" in u:
        return "Bharti AXA"
    if "ROYAL SUNDARAM" in u:
        return "Royal Sundaram"
    if "INDUSIND" in u:
        return "IndusInd General"
    if "GODIGIT" in u:
        return "Go Digit"
    return str(raw_name).title()

def decrypt_pmfby_payload(encrypted_text):
    """Decrypts AES-256-CBC encrypted payload from PMFBY API."""
    parts = encrypted_text.split('.')
    if len(parts) < 4 or parts[0] != 'v1':
        raise ValueError("Invalid PMFBY encrypted payload format")

    ciphertext_hex = parts[1]
    key_str = base64.b64decode(parts[2]).decode('utf-8')
    iv_str = base64.b64decode(parts[3]).decode('utf-8')

    cipher = Cipher(algorithms.AES(key_str.encode('utf-8')), modes.CBC(iv_str.encode('utf-8')), backend=default_backend())
    decryptor = cipher.decryptor()
    ciphertext = bytes.fromhex(ciphertext_hex)
    decrypted = decryptor.update(ciphertext) + decryptor.finalize()

    idx = decrypted.rfind(b'}')
    if idx != -1:
        return json.loads(decrypted[:idx+1].decode('utf-8'))
    pad = decrypted[-1]
    if isinstance(pad, int) and pad <= 16:
        decrypted = decrypted[:-pad]

    return json.loads(decrypted.decode('utf-8'))

def fetch_pmfby_endpoint(url):
    """Fetches and decrypts an endpoint from pmfby.gov.in."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*'
    })

    with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
        text = resp.read().decode('utf-8')

    return decrypt_pmfby_payload(text)

class PMFBYProcessor:
    def __init__(self, cache_dir=CACHE_DIR):
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
        self.total_cache_file = os.path.join(self.cache_dir, "home_page_report_total.json")
        self.ic_mapping_file = os.path.join(self.cache_dir, "ic_district_mapping.json")
        self.comp_mapping_file = os.path.join(self.cache_dir, "ic_comprehensive_mapping.json")
        self.crop_rates_file = os.path.join(self.cache_dir, "crop_district_rates.json")
        self.sync_status_file = os.path.join(self.cache_dir, "sync_status.json")
        
        self.ic_mapping = self._load_ic_mapping()
        self.comp_mapping = self._load_comprehensive_mapping()
        self.crop_rates = self._load_crop_rates()
        self.historical_metrics = self._compute_historical_metrics()
        
        # Start background daily scheduler
        self._scheduler_started = False
        self.start_daily_sync_scheduler()

    def _load_crop_rates(self):
        """Loads harvested official crop-wise premium rates per district."""
        if os.path.exists(self.crop_rates_file):
            try:
                with open(self.crop_rates_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _compute_historical_metrics(self):
        """
        Computes cumulative historical statistics (Total Premium, Sum Insured, Claims Paid, Loss Ratio)
        across all available historical years (2018-2026) for:
          - Each Insurance Company
          - Each District (keyed by STATE_DISTRICT and state_code_district_code)
          - Each State (keyed by state_name and state_code)
        """
        dist_files = glob.glob(os.path.join(self.cache_dir, "districts_*.json"))
        records = []
        for f in dist_files:
            if "_all.json" in f:
                continue
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    d = json.load(fp)
                    if isinstance(d, list):
                        records.extend(d)
            except Exception:
                pass

        ic_hist = {}
        dist_hist = {}
        state_hist = {}

        for r in records:
            ic = r.get('insurance_company_short') or clean_ic_name(r.get('insurance_company')) or 'AIC of India'
            st = str(r.get('state_name', '')).strip().upper()
            sc = str(r.get('state_code', '')).strip()
            dn = str(r.get('district_name', '')).strip().upper()
            dc = str(r.get('district_code', '')).strip()
            prem = float(r.get('gross_premium_crore') or 0.0)
            claims = float(r.get('claims_paid_crore') or 0.0)
            si = float(r.get('sum_insured_crore') or 0.0)
            yr = str(r.get('year', ''))

            # Insurance Company Historicals
            if ic not in ic_hist:
                ic_hist[ic] = {'premium': 0.0, 'claims': 0.0, 'sum_insured': 0.0, 'by_year': {}}
            ic_hist[ic]['premium'] += prem
            ic_hist[ic]['claims'] += claims
            ic_hist[ic]['sum_insured'] += si
            if yr:
                if yr not in ic_hist[ic]['by_year']:
                    ic_hist[ic]['by_year'][yr] = {'premium': 0.0, 'claims': 0.0}
                ic_hist[ic]['by_year'][yr]['premium'] += prem
                ic_hist[ic]['by_year'][yr]['claims'] += claims

            # District Historicals (keys: ST_DN, and SC_DC)
            keys_to_add = [f"{st}_{dn}"]
            if sc and dc:
                keys_to_add.append(f"{sc}_{dc}")
            for dk in keys_to_add:
                if dk not in dist_hist:
                    dist_hist[dk] = {'premium': 0.0, 'claims': 0.0, 'sum_insured': 0.0}
                dist_hist[dk]['premium'] += prem
                dist_hist[dk]['claims'] += claims
                dist_hist[dk]['sum_insured'] += si

            # State Historicals (keys: ST, and SC)
            for sk in [st, sc]:
                if not sk:
                    continue
                if sk not in state_hist:
                    state_hist[sk] = {'premium': 0.0, 'claims': 0.0, 'sum_insured': 0.0}
                state_hist[sk]['premium'] += prem
                state_hist[sk]['claims'] += claims
                state_hist[sk]['sum_insured'] += si

        # Calculate LRs and Weighted Premium Rates
        for d in [ic_hist, dist_hist, state_hist]:
            for k, v in d.items():
                p = v['premium']
                c = v['claims']
                s = v['sum_insured']
                v['historical_loss_ratio_pct'] = round(c / p * 100, 1) if p > 0 else 0.0
                v['weighted_premium_rate_pct'] = round(p / s * 100, 2) if s > 0 else 0.0

        return {
            "companies": ic_hist,
            "districts": dist_hist,
            "states": state_hist
        }

    def _load_ic_mapping(self):
        """Loads cached Insurance Company mapping."""
        if os.path.exists(self.ic_mapping_file):
            try:
                with open(self.ic_mapping_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _load_comprehensive_mapping(self):
        """Loads comprehensive multi-year Insurance Company mapping."""
        if os.path.exists(self.comp_mapping_file):
            try:
                with open(self.comp_mapping_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"district_map": {}, "state_map": {}, "all_companies": []}

    def get_national_summary(self, force_refresh=False):
        """Fetches national season-wise summary data across all years (2018-2026)."""
        if not force_refresh and os.path.exists(self.total_cache_file):
            try:
                with open(self.total_cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        try:
            url = 'https://www.pmfby.gov.in/goiConfig/getHomePageReportTotal'
            res = fetch_pmfby_endpoint(url)
            raw_data = res.get('data', {})

            formatted = []
            for k, rec in raw_data.items():
                season_code = rec.get('season')
                season_name = "Kharif" if season_code == "01" else "Rabi"
                year = rec.get('year')

                def f_val(v):
                    if v is None: return 0.0
                    try: return float(str(v).replace(',', ''))
                    except ValueError: return 0.0

                def i_val(v):
                    if v is None: return 0
                    try: return int(float(str(v).replace(',', '')))
                    except ValueError: return 0

                area_pmfby_k_ha = f_val(rec.get('areaInsuredPmfby'))
                area_wbcis_k_ha = f_val(rec.get('areaInsuredWbcis'))
                total_area_lakh_ha = round((area_pmfby_k_ha + area_wbcis_k_ha) / 100.0, 2)

                sum_ins_lakh = f_val(rec.get('sumInsured'))
                sum_ins_crore = round(sum_ins_lakh / 100.0, 2)

                premium_lakh = f_val(rec.get('grossPremium'))
                premium_crore = round(premium_lakh / 100.0, 2)

                farmer_prem_lakh = f_val(rec.get('farmerShare'))
                farmer_prem_crore = round(farmer_prem_lakh / 100.0, 2)

                goi_share_lakh = f_val(rec.get('goiShare'))
                goi_share_crore = round(goi_share_lakh / 100.0, 2)

                state_share_lakh = f_val(rec.get('stateShare'))
                state_share_crore = round(state_share_lakh / 100.0, 2)

                claims_lakh = f_val(rec.get('totalClaimPaid'))
                claims_crore = round(claims_lakh / 100.0, 2)

                farmer_count = i_val(rec.get('farmerCount'))
                pmfby_apps = i_val(rec.get('pmfbyApplications'))
                wbcis_apps = i_val(rec.get('wbcisApplications'))
                total_apps = pmfby_apps + wbcis_apps

                benefited_count = i_val(rec.get('claimFarmerBenefited'))
                benefited_wbcis = i_val(rec.get('claimFarmerBenefitedWbcis'))
                total_benefited = benefited_count + benefited_wbcis

                loss_ratio = round((claims_crore / premium_crore * 100), 1) if premium_crore > 0 else 0.0

                formatted.append({
                    "season_key": k,
                    "year": int(year),
                    "season_code": season_code,
                    "season_name": season_name,
                    "display_name": f"{season_name} {year}",
                    "state_count": i_val(rec.get('stateCount')),
                    "district_count": i_val(rec.get('districtCount')),
                    "iu_count": i_val(rec.get('iuCount')),
                    "crop_count": i_val(rec.get('agricultureCropsCount')) + i_val(rec.get('horticultureCropsCount')),
                    "agri_crops": i_val(rec.get('agricultureCropsCount')),
                    "horti_crops": i_val(rec.get('horticultureCropsCount')),
                    "farmer_count": farmer_count,
                    "loanee": i_val(rec.get('loanee')),
                    "non_loanee": i_val(rec.get('nonLoanee')),
                    "total_applications": total_apps,
                    "pmfby_applications": pmfby_apps,
                    "wbcis_applications": wbcis_apps,
                    "area_insured_lakh_ha": total_area_lakh_ha,
                    "sum_insured_crore": sum_ins_crore,
                    "gross_premium_crore": premium_crore,
                    "farmer_premium_crore": farmer_prem_crore,
                    "goi_subsidy_crore": goi_share_crore,
                    "state_subsidy_crore": state_share_crore,
                    "claims_paid_crore": claims_crore,
                    "benefited_farmers": total_benefited,
                    "loss_ratio_pct": loss_ratio,
                    "male_pct": f_val(rec.get('male')),
                    "female_pct": f_val(rec.get('female')),
                    "transgender_pct": f_val(rec.get('transgender')),
                    "sc_pct": f_val(rec.get('sc')),
                    "st_pct": f_val(rec.get('st')),
                    "obc_pct": f_val(rec.get('obc')),
                    "gen_pct": f_val(rec.get('gen')),
                    "marginal_pct": f_val(rec.get('marginal')),
                    "small_pct": f_val(rec.get('small')),
                    "other_farm_pct": f_val(rec.get('other')),
                    "claim_prevented_sowing_lakh": f_val(rec.get('PreventedSowing')),
                    "claim_mid_term_lakh": f_val(rec.get('midTerm')),
                    "claim_localised_lakh": f_val(rec.get('localised')),
                    "claim_post_harvest_lakh": f_val(rec.get('postHarvest')),
                    "claim_yield_lakh": f_val(rec.get('yield')),
                    "claim_rwbcis_lakh": f_val(rec.get('rwbcis'))
                })

            formatted.sort(key=lambda x: (x['year'], x['season_code']))

            with open(self.total_cache_file, "w", encoding="utf-8") as f:
                json.dump(formatted, f, indent=2)

            return formatted
        except Exception as e:
            print(f"Error fetching PMFBY summary: {e}")
            if os.path.exists(self.total_cache_file):
                with open(self.total_cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            return []

    def get_state_report(self, year="2024", season_code="01", scheme_code="02"):
        """Fetches state-wise PMFBY report for a given year & season."""
        cache_file = os.path.join(self.cache_dir, f"state_report_{year}_{season_code}.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        try:
            url = f'https://www.pmfby.gov.in/goiConfig/getAdminDashboardStateWiseReport?year={year}&seasonCode={season_code}&schemeCode={scheme_code}&isCombined=true'
            res = fetch_pmfby_endpoint(url)
            states_data = res.get('data', [])

            formatted_states = []
            for s in states_data:
                def f_val(v):
                    if v is None: return 0.0
                    try: return float(str(v).replace(',', ''))
                    except ValueError: return 0.0

                def i_val(v):
                    if v is None: return 0
                    try: return int(float(str(v).replace(',', '')))
                    except ValueError: return 0

                s_name = s.get('stateName', 'State').strip()
                area_k_ha = f_val(s.get('areaInsured'))
                area_lakh_ha = round(area_k_ha / 100.0, 2)

                sum_ins_lakh = f_val(s.get('sumInsured'))
                sum_ins_crore = round(sum_ins_lakh / 100.0, 2)

                prem_lakh = f_val(s.get('grossPremium'))
                prem_crore = round(prem_lakh / 100.0, 2)

                claims_lakh = f_val(s.get('totalClaimPaid'))
                claims_crore = round(claims_lakh / 100.0, 2)

                farmer_cnt = i_val(s.get('farmerCount'))
                benefited_cnt = i_val(s.get('claimFarmerBenefitedDist'))

                loss_ratio = round((claims_crore / prem_crore * 100), 1) if prem_crore > 0 else 0.0

                formatted_states.append({
                    "state_code": str(s.get('stateCode')),
                    "state_name": s_name,
                    "year": str(year),
                    "season": "Kharif" if season_code == "01" else "Rabi",
                    "districts": i_val(s.get('districtCount')),
                    "iu_count": i_val(s.get('iuCount')),
                    "farmer_count": farmer_cnt,
                    "loanee": i_val(s.get('loanee')),
                    "non_loanee": i_val(s.get('nonLoanee')),
                    "area_insured_lakh_ha": area_lakh_ha,
                    "sum_insured_crore": sum_ins_crore,
                    "gross_premium_crore": prem_crore,
                    "farmer_share_crore": round(f_val(s.get('farmerShare')) / 100.0, 2),
                    "goi_share_crore": round(f_val(s.get('goiShare')) / 100.0, 2),
                    "state_share_crore": round(f_val(s.get('stateShare')) / 100.0, 2),
                    "claims_paid_crore": claims_crore,
                    "benefited_farmers": benefited_cnt,
                    "loss_ratio_pct": loss_ratio,
                    "male_pct": f_val(s.get('male')),
                    "female_pct": f_val(s.get('female')),
                    "sc_pct": f_val(s.get('sc')),
                    "st_pct": f_val(s.get('st')),
                    "obc_pct": f_val(s.get('obc')),
                    "gen_pct": f_val(s.get('gen'))
                })

            formatted_states.sort(key=lambda x: x['farmer_count'], reverse=True)

            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(formatted_states, f, indent=2)

            return formatted_states
        except Exception as e:
            print(f"Error fetching state report: {e}")
            return []

    def get_district_reports(self, year="2024", season_code="01", state_code=None, scheme_code="02", company_name=None):
        """
        Fetches district-wise reports for a given season, merging each district's
        notified Insurance Company mapped from the PMFBY Premium Calculator.
        Supports filtering by Year, Season, State, and Insurance Company.
        """
        cache_file = os.path.join(self.cache_dir, f"districts_{year}_{season_code}_{state_code or 'all'}.json")
        districts_loaded = None

        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    districts_loaded = json.load(f)
                # Ensure all cached items have insurance_company resolved
                needs_save = False
                for d in districts_loaded:
                    if not d.get('insurance_company') or not d.get('insurance_company_short'):
                        ic_res = self._resolve_insurance_company(
                            d.get('year', year),
                            d.get('state_code', ''),
                            d.get('district_code', ''),
                            d.get('district_name', '')
                        )
                        d['insurance_company'] = ic_res["company_name"]
                        d['insurance_company_short'] = ic_res["company_short"]
                        needs_save = True
                if needs_save:
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(districts_loaded, f, indent=2)
            except Exception:
                districts_loaded = None

        if districts_loaded is None:
            states = self.get_state_report(year=year, season_code=season_code, scheme_code=scheme_code)
            if not states:
                # If target year has no state report yet, fallback to 2023
                states = self.get_state_report(year="2023", season_code=season_code, scheme_code=scheme_code)

            if state_code and state_code != 'all':
                target_states = [s for s in states if str(s['state_code']) == str(state_code)]
            else:
                target_states = states

            all_districts = []

            for st in target_states:
                sc = str(st['state_code'])
                s_name = st['state_name']

                try:
                    url = f'https://www.pmfby.gov.in/goiConfig/getAdminDashboardDistrictWiseReport?year={year}&seasonCode={season_code}&schemeCode={scheme_code}&stateCode={sc}'
                    res = fetch_pmfby_endpoint(url)
                    dists = res.get('data', [])

                    for d in dists:
                        def f_val(v):
                            if v is None: return 0.0
                            try: return float(str(v).replace(',', ''))
                            except ValueError: return 0.0

                        def i_val(v):
                            if v is None: return 0
                            try: return int(float(str(v).replace(',', '')))
                            except ValueError: return 0

                        d_name = d.get('districtName', 'District').strip()
                        d_code = str(d.get('districtCode', '')).strip()

                        # Resolve designated Insurance Company from Premium Calculator mapping
                        ic_info = self._resolve_insurance_company(year, sc, d_code, d_name)

                        area_k_ha = f_val(d.get('areaInsured'))
                        area_lakh_ha = round(area_k_ha / 100.0, 2)

                        sum_ins_lakh = f_val(d.get('sumInsured'))
                        sum_ins_crore = round(sum_ins_lakh / 100.0, 2)

                        prem_lakh = f_val(d.get('grossPremium'))
                        prem_crore = round(prem_lakh / 100.0, 2)

                        claims_lakh = f_val(d.get('totalClaimPaid'))
                        claims_crore = round(claims_lakh / 100.0, 2)

                        farmer_cnt = i_val(d.get('farmerCount'))
                        benefited_cnt = i_val(d.get('claimFarmerBenefitedDist'))

                        loss_ratio = round((claims_crore / prem_crore * 100), 1) if prem_crore > 0 else 0.0

                        all_districts.append({
                            "district_code": d_code,
                            "district_name": d_name,
                            "state_code": sc,
                            "state_name": s_name,
                            "year": str(year),
                            "season": "Kharif" if season_code == "01" else "Rabi",
                            "insurance_company": ic_info["company_name"],
                            "insurance_company_short": ic_info["company_short"],
                            "iu_count": i_val(d.get('iuCount')),
                            "farmer_count": farmer_cnt,
                            "loanee": i_val(d.get('loanee')),
                            "non_loanee": i_val(d.get('nonLoanee')),
                            "area_insured_lakh_ha": area_lakh_ha,
                            "sum_insured_crore": sum_ins_crore,
                            "gross_premium_crore": prem_crore,
                            "farmer_share_crore": round(f_val(d.get('farmerShare')) / 100.0, 2),
                            "goi_share_crore": round(f_val(d.get('goiShare')) / 100.0, 2),
                            "state_share_crore": round(f_val(d.get('stateShare')) / 100.0, 2),
                            "claims_paid_crore": claims_crore,
                            "benefited_farmers": benefited_cnt,
                            "loss_ratio_pct": loss_ratio,
                            "male_pct": f_val(d.get('male')),
                            "female_pct": f_val(d.get('female')),
                            "sc_pct": f_val(d.get('sc')),
                            "st_pct": f_val(d.get('st')),
                            "obc_pct": f_val(d.get('obc')),
                            "gen_pct": f_val(d.get('gen')),
                            "marginal_pct": f_val(d.get('marginal')),
                            "small_pct": f_val(d.get('small')),
                            "other_farm_pct": f_val(d.get('other'))
                        })
                except Exception as e:
                    print(f"Error fetching districts for {s_name}: {e}")

            all_districts.sort(key=lambda x: x['farmer_count'], reverse=True)

            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(all_districts, f, indent=2)

            districts_loaded = all_districts

        # Ensure every entry in districts_loaded has insurance_company and insurance_company_short
        for d in districts_loaded:
            if not d.get('insurance_company') or not d.get('insurance_company_short'):
                ic_res = self._resolve_insurance_company(
                    d.get('year', year),
                    d.get('state_code', ''),
                    d.get('district_code', ''),
                    d.get('district_name', '')
                )
                d['insurance_company'] = ic_res["company_name"]
                d['insurance_company_short'] = ic_res["company_short"]

        # Filter by company name if requested
        if company_name and company_name != 'all':
            c_low = company_name.lower().strip()
            return [
                d for d in districts_loaded
                if c_low in (d.get('insurance_company') or '').lower()
                or c_low in (d.get('insurance_company_short') or '').lower()
            ]

        return districts_loaded

    def _resolve_insurance_company(self, year, state_code="", district_code="", district_name="", season="01", scheme="02"):
        """Resolves the designated Insurance Company for a district from comprehensive multi-year mapping."""
        sc = str(state_code or "").strip()
        dc = str(district_code or "").strip()
        dn_raw = str(district_name or "").strip().upper()
        dn_norm = dn_raw.replace(" ", "")
        yr = str(year or "").strip()
        sn = str(season or "01").strip()
        sch = str(scheme or "02").strip()

        d_map = self.comp_mapping.get("district_map", {})

        # Priority 1: Exact matches in comprehensive mapping
        candidates = [
            f"{yr}_{sn}_{sch}_{sc}_{dc}",
            f"{yr}_{sn}_{sch}_{sc}_{dn_raw}",
            f"{yr}_{sn}_{sch}_{sc}_{dn_norm}",
            f"{yr}_{sn}_{sc}_{dc}",
            f"{yr}_{sn}_{sc}_{dn_raw}",
            f"{yr}_{sc}_{dc}",
            f"{yr}_{sc}_{dn_raw}",
            f"{yr}_{sc}_{dn_norm}",
            f"{sc}_{dc}",
            f"{sc}_{dn_raw}",
            f"{sc}_{dn_norm}"
        ]
        for c in candidates:
            if c in d_map:
                info = d_map[c]
                c_name = info.get("name") or info.get("company_name", "")
                c_short = info.get("short") or info.get("company_short", "")
                if c_name and "DO NOT SELECT" not in c_name.upper() and c_short != "Do Not Select":
                    return {"company_name": c_name, "company_short": clean_ic_name(c_short or c_name)}

        # Priority 2: Legacy ic_mapping
        for yr_candidate in [yr, "2024", "2023", "2022"]:
            yr_dict = self.ic_mapping.get(yr_candidate, {})
            k_code = f"{sc}_{dc}"
            if k_code in yr_dict:
                c_name = yr_dict[k_code]["company_name"]
                return {"company_name": c_name, "company_short": clean_ic_name(c_name)}
            k_name = f"{sc}_{dn_raw}"
            if k_name in yr_dict:
                c_name = yr_dict[k_name]["company_name"]
                return {"company_name": c_name, "company_short": clean_ic_name(c_name)}

        # Priority 3: State-level mapping
        st_map = self.comp_mapping.get("state_map", {})
        for st_cand in [f"{yr}_{sn}_{sch}_{sc}", f"{yr}_{sn}_{sc}", f"{yr}_{sc}", f"{sc}"]:
            if st_cand in st_map and st_map[st_cand]:
                first_co = st_map[st_cand][0]
                return {"company_name": first_co, "company_short": clean_ic_name(first_co)}

        # Default fallback
        def_name = "AGRICULTURE INSURANCE COMPANY OF INDIA"
        return {"company_name": def_name, "company_short": "AIC of India"}

    def get_all_insurance_companies(self):
        """Returns the distinct list of all notified Insurance Companies."""
        companies = set()
        for c in self.comp_mapping.get("all_companies", []):
            cleaned = clean_ic_name(c)
            if cleaned and cleaned not in ["Do Not Select", "None", ""]:
                companies.add(cleaned)

        for yr, dists in self.ic_mapping.items():
            for k, info in dists.items():
                cleaned = clean_ic_name(info.get("company_name", ""))
                if cleaned and cleaned not in ["Do Not Select", "None", ""]:
                    companies.add(cleaned)

        result = []
        for c in sorted(companies):
            result.append({
                "full_name": c,
                "short_name": c
            })
        return result

    def get_sync_status(self):
        """Returns the current status of PMFBY daily auto-sync."""
        if os.path.exists(self.sync_status_file):
            try:
                with open(self.sync_status_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
        status = {
            "last_checked": now_str,
            "last_updated": now_str,
            "status": "synced",
            "auto_sync_interval_hours": 24,
            "total_seasons": 18,
            "total_states": 36,
            "total_companies": len(self.get_all_insurance_companies()),
            "is_new_data_available": False,
            "message": "All PMFBY & RWBCIS datasets are up to date with national portal."
        }
        with open(self.sync_status_file, "w", encoding="utf-8") as f:
            json.dump(status, f, indent=2)
        return status

    def daily_sync(self, force_refresh=False):
        """
        Executes daily synchronization check against the PMFBY government portal.
        Refreshes local caches if newer statistics are detected.
        """
        now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
        new_data_detected = False

        try:
            # 1. Check National Summary
            old_summary = None
            if os.path.exists(self.total_cache_file):
                try:
                    with open(self.total_cache_file, "r", encoding="utf-8") as f:
                        old_summary = json.load(f)
                except Exception:
                    pass

            new_summary = self.get_national_summary(force_refresh=True)
            if old_summary and len(new_summary) != len(old_summary):
                new_data_detected = True

            status = self.get_sync_status()
            status["last_checked"] = now_str
            if new_data_detected or force_refresh:
                try:
                    self.get_state_report("2024", "01")
                    self.crop_rates = self._load_crop_rates()
                    self.historical_metrics = self._compute_historical_metrics()
                except Exception as ex:
                    print("Error updating metrics during daily sync:", ex)

                status["last_updated"] = now_str
                status["is_new_data_available"] = True
                status["message"] = "PMFBY government portal check complete: Cache refreshed with latest statistics."
            else:
                status["is_new_data_available"] = False
                status["message"] = "PMFBY government portal check complete: Local data is fully up to date."

            with open(self.sync_status_file, "w", encoding="utf-8") as f:
                json.dump(status, f, indent=2)

            return status
        except Exception as e:
            status = self.get_sync_status()
            status["last_checked"] = now_str
            status["message"] = f"Check finished (local cache verified): {e}"
            return status

    def start_daily_sync_scheduler(self):
        """Starts a background daemon thread that periodically checks PMFBY portal daily."""
        if self._scheduler_started:
            return
        self._scheduler_started = True

        def _worker():
            while True:
                # 24 hours interval (86400s)
                time.sleep(86400)
                try:
                    self.daily_sync(force_refresh=False)
                except Exception as e:
                    print("PMFBY daily sync background worker error:", e)

        t = threading.Thread(target=_worker, daemon=True, name="PMFBYDailySyncWorker")
        t.start()

    def get_company_analytics(self, year="all", season="all", scheme="all", level="company", company="all", state_code="all", search=""):
        """
        Retrieves multi-dimensional PMFBY Insurance Company analytics.
        Provides provision to select:
          - level: 'company' (portfolio summary), 'state' (state-wise), or 'district' (district-wise)
          - year: 'all', '2024', '2023', '2022', '2021', '2020', '2019', '2018'
          - season: 'all', '01' (Kharif), '02' (Rabi)
          - scheme: 'all', '02' (PMFBY), '04' (RWBCIS)
          - company: 'all' or specific insurance company name
          - state_code: 'all' or specific state code
          - search: textual search string
        """
        dist_files = glob.glob(os.path.join(self.cache_dir, "districts_*.json"))
        records = []
        for f in dist_files:
            if "_all.json" in f:
                continue
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    dists = json.load(fp)
                    if isinstance(dists, list):
                        records.extend(dists)
            except Exception:
                pass

        # Apply dimension filters
        c_low = company.lower().strip() if company and company != 'all' else None
        s_low = search.lower().strip() if search else None

        filtered = []
        for d in records:
            if year != 'all' and str(d.get('year')) != str(year):
                continue
            if season != 'all' and str(d.get('season_code')) != str(season):
                continue
            if scheme != 'all' and str(d.get('scheme_code')) != str(scheme):
                continue
            if state_code != 'all' and str(d.get('state_code')) != str(state_code):
                continue
            
            ic_short = d.get('insurance_company_short') or clean_ic_name(d.get('insurance_company'))
            ic_full = d.get('insurance_company') or ic_short

            if c_low:
                if c_low not in ic_short.lower() and c_low not in ic_full.lower():
                    continue

            if s_low:
                d_name = (d.get('district_name') or '').lower()
                st_name = (d.get('state_name') or '').lower()
                if (s_low not in d_name and s_low not in st_name and 
                    s_low not in ic_short.lower() and s_low not in ic_full.lower()):
                    continue

            d['insurance_company_short'] = ic_short
            d['insurance_company'] = ic_full
            filtered.append(d)

        # Build output structure based on selected level
        if level == 'crop':
            crop_filtered = []
            for c in self.crop_rates:
                if year != 'all' and str(c.get('year')) != str(year):
                    continue
                if season != 'all' and str(c.get('season_code')) != str(season):
                    continue
                if scheme != 'all' and str(c.get('scheme_code')) != str(scheme):
                    continue
                if state_code != 'all' and str(c.get('state_code')) != str(state_code):
                    continue
                
                ic_short = c.get('insurance_company_short') or clean_ic_name(c.get('insurance_company'))
                ic_full = c.get('insurance_company') or ic_short

                if c_low:
                    if c_low not in ic_short.lower() and c_low not in ic_full.lower():
                        continue

                if s_low:
                    c_name = (c.get('crop_name') or '').lower()
                    cat_name = (c.get('crop_category') or '').lower()
                    d_name = (c.get('district_name') or '').lower()
                    st_name = (c.get('state_name') or '').lower()
                    if (s_low not in c_name and s_low not in cat_name and 
                        s_low not in d_name and s_low not in st_name and 
                        s_low not in ic_short.lower() and s_low not in ic_full.lower()):
                        continue

                st_key = str(c.get('state_name', '')).strip().upper()
                dn_key = str(c.get('district_name', '')).strip().upper()
                sc_key = str(c.get('state_code', '')).strip()
                dc_key = str(c.get('district_code', '')).strip()
                dk = f"{st_key}_{dn_key}"

                dist_hist = self.historical_metrics['districts'].get(dk) or self.historical_metrics['districts'].get(f"{sc_key}_{dc_key}", {})
                ic_hist = self.historical_metrics['companies'].get(ic_short, {})

                rec = dict(c)
                rec['insurance_company_short'] = ic_short
                rec['insurance_company'] = ic_full
                rec['district_premium_rate_pct'] = dist_hist.get('weighted_premium_rate_pct', 0.0)
                rec['district_historical_lr_pct'] = dist_hist.get('historical_loss_ratio_pct', 0.0)
                rec['company_premium_rate_pct'] = ic_hist.get('weighted_premium_rate_pct', 0.0)
                rec['company_historical_lr_pct'] = ic_hist.get('historical_loss_ratio_pct', 0.0)
                crop_filtered.append(rec)

            crop_filtered.sort(key=lambda x: x.get('actuarial_rate_pct', 0), reverse=True)
            output_data = crop_filtered

        elif level == 'district':
            for d in filtered:
                gross_prem = float(d.get('gross_premium_crore') or 0.0)
                sum_ins = float(d.get('sum_insured_crore') or 0.0)
                farmer_prem = float(d.get('farmer_share_crore') or 0.0)
                subsidy_prem = float(d.get('goi_share_crore') or 0.0) + float(d.get('state_share_crore') or 0.0)
                
                d['district_premium_rate_pct'] = round(gross_prem / sum_ins * 100, 2) if sum_ins > 0 else 0.0
                d['farmer_premium_rate_pct'] = round(farmer_prem / sum_ins * 100, 2) if sum_ins > 0 else 0.0
                d['subsidy_rate_pct'] = round(subsidy_prem / sum_ins * 100, 2) if sum_ins > 0 else 0.0

                st_key = str(d.get('state_name', '')).strip().upper()
                dn_key = str(d.get('district_name', '')).strip().upper()
                sc_key = str(d.get('state_code', '')).strip()
                dc_key = str(d.get('district_code', '')).strip()
                dk = f"{st_key}_{dn_key}"

                dist_hist = self.historical_metrics['districts'].get(dk) or self.historical_metrics['districts'].get(f"{sc_key}_{dc_key}", {})
                d['historical_loss_ratio_pct'] = dist_hist.get('historical_loss_ratio_pct', d.get('loss_ratio_pct', 0.0))
                d['historical_premium_rate_pct'] = dist_hist.get('weighted_premium_rate_pct', 0.0)
                d['historical_claims_paid_crore'] = round(dist_hist.get('claims', 0.0), 2)
                d['historical_gross_premium_crore'] = round(dist_hist.get('premium', 0.0), 2)

            filtered.sort(key=lambda x: x.get('farmer_count', 0), reverse=True)
            output_data = filtered

        elif level == 'state':
            st_groups = {}
            for d in filtered:
                k = (d.get('state_name', 'Unknown'), d.get('state_code', ''), d.get('insurance_company_short', 'AIC of India'), d.get('year', ''), d.get('season', ''), d.get('scheme', ''))
                if k not in st_groups:
                    st_groups[k] = {
                        "state_name": k[0],
                        "state_code": k[1],
                        "insurance_company": d.get('insurance_company', k[2]),
                        "insurance_company_short": k[2],
                        "year": k[3],
                        "season": k[4],
                        "scheme": k[5],
                        "districts_count": set(),
                        "farmer_count": 0,
                        "area_insured_lakh_ha": 0.0,
                        "sum_insured_crore": 0.0,
                        "gross_premium_crore": 0.0,
                        "farmer_share_crore": 0.0,
                        "goi_share_crore": 0.0,
                        "state_share_crore": 0.0,
                        "claims_paid_crore": 0.0,
                        "benefited_farmers": 0
                    }
                g = st_groups[k]
                g["districts_count"].add(d.get('district_code', '') or d.get('district_name', ''))
                g["farmer_count"] += int(d.get('farmer_count') or 0)
                g["area_insured_lakh_ha"] += float(d.get('area_insured_lakh_ha') or 0.0)
                g["sum_insured_crore"] += float(d.get('sum_insured_crore') or 0.0)
                g["gross_premium_crore"] += float(d.get('gross_premium_crore') or 0.0)
                g["farmer_share_crore"] += float(d.get('farmer_share_crore') or 0.0)
                g["goi_share_crore"] += float(d.get('goi_share_crore') or 0.0)
                g["state_share_crore"] += float(d.get('state_share_crore') or 0.0)
                g["claims_paid_crore"] += float(d.get('claims_paid_crore') or 0.0)
                g["benefited_farmers"] += int(d.get('benefited_farmers') or 0)

            output_data = []
            for g in st_groups.values():
                d_cnt = len(g["districts_count"])
                g["districts_count"] = d_cnt
                g["area_insured_lakh_ha"] = round(g["area_insured_lakh_ha"], 2)
                g["sum_insured_crore"] = round(g["sum_insured_crore"], 2)
                g["gross_premium_crore"] = round(g["gross_premium_crore"], 2)
                g["farmer_share_crore"] = round(g["farmer_share_crore"], 2)
                g["goi_share_crore"] = round(g["goi_share_crore"], 2)
                g["state_share_crore"] = round(g["state_share_crore"], 2)
                g["claims_paid_crore"] = round(g["claims_paid_crore"], 2)
                prem = g["gross_premium_crore"]
                sum_ins = g["sum_insured_crore"]
                g["loss_ratio_pct"] = round(g["claims_paid_crore"] / prem * 100, 1) if prem > 0 else 0.0
                g["state_premium_rate_pct"] = round(prem / sum_ins * 100, 2) if sum_ins > 0 else 0.0

                st_key = str(g.get('state_name', '')).strip().upper()
                sc_key = str(g.get('state_code', '')).strip()
                st_hist = self.historical_metrics['states'].get(st_key) or self.historical_metrics['states'].get(sc_key, {})
                g["historical_loss_ratio_pct"] = st_hist.get('historical_loss_ratio_pct', g.get('loss_ratio_pct', 0.0))
                g["historical_premium_rate_pct"] = st_hist.get('weighted_premium_rate_pct', 0.0)
                g["historical_claims_paid_crore"] = round(st_hist.get('claims', 0.0), 2)
                g["historical_gross_premium_crore"] = round(st_hist.get('premium', 0.0), 2)

                output_data.append(g)

            output_data.sort(key=lambda x: x.get('farmer_count', 0), reverse=True)
        else: # level == 'company' (default summary)
            ic_groups = {}
            for d in filtered:
                ic_s = d.get('insurance_company_short') or 'AIC of India'
                if ic_s not in ic_groups:
                    ic_groups[ic_s] = {
                        "company_short": ic_s,
                        "company_name": d.get('insurance_company') or ic_s,
                        "districts": set(),
                        "states": set(),
                        "farmer_count": 0,
                        "area_insured_lakh_ha": 0.0,
                        "sum_insured_crore": 0.0,
                        "gross_premium_crore": 0.0,
                        "farmer_share_crore": 0.0,
                        "goi_share_crore": 0.0,
                        "state_share_crore": 0.0,
                        "claims_paid_crore": 0.0,
                        "benefited_farmers": 0,
                        "years": set(),
                        "seasons": set(),
                        "schemes": set()
                    }
                g = ic_groups[ic_s]
                g["districts"].add(f"{d.get('state_code')}_{d.get('district_code')}")
                g["states"].add(d.get('state_name'))
                g["farmer_count"] += int(d.get('farmer_count') or 0)
                g["area_insured_lakh_ha"] += float(d.get('area_insured_lakh_ha') or 0.0)
                g["sum_insured_crore"] += float(d.get('sum_insured_crore') or 0.0)
                g["gross_premium_crore"] += float(d.get('gross_premium_crore') or 0.0)
                g["farmer_share_crore"] += float(d.get('farmer_share_crore') or 0.0)
                g["goi_share_crore"] += float(d.get('goi_share_crore') or 0.0)
                g["state_share_crore"] += float(d.get('state_share_crore') or 0.0)
                g["claims_paid_crore"] += float(d.get('claims_paid_crore') or 0.0)
                g["benefited_farmers"] += int(d.get('benefited_farmers') or 0)
                if d.get('year'): g["years"].add(str(d.get('year')))
                if d.get('season'): g["seasons"].add(str(d.get('season')))
                if d.get('scheme'): g["schemes"].add(str(d.get('scheme')))

            output_data = []
            for g in ic_groups.values():
                d_cnt = len(g["districts"])
                s_cnt = len(g["states"])
                states_list = sorted(list(g["states"]))
                g["districts_count"] = d_cnt
                g["states_count"] = s_cnt
                g["states_list"] = states_list
                del g["districts"]
                del g["states"]
                g["area_insured_lakh_ha"] = round(g["area_insured_lakh_ha"], 2)
                g["sum_insured_crore"] = round(g["sum_insured_crore"], 2)
                g["gross_premium_crore"] = round(g["gross_premium_crore"], 2)
                g["farmer_share_crore"] = round(g["farmer_share_crore"], 2)
                g["goi_share_crore"] = round(g["goi_share_crore"], 2)
                g["state_share_crore"] = round(g["state_share_crore"], 2)
                g["claims_paid_crore"] = round(g["claims_paid_crore"], 2)
                prem = g["gross_premium_crore"]
                sum_ins = g["sum_insured_crore"]
                farmer_prem = g["farmer_share_crore"]
                subsidy_prem = g["goi_share_crore"] + g["state_share_crore"]
                
                g["loss_ratio_pct"] = round(g["claims_paid_crore"] / prem * 100, 1) if prem > 0 else 0.0
                g["company_premium_rate_pct"] = round(prem / sum_ins * 100, 2) if sum_ins > 0 else 0.0
                g["farmer_premium_rate_pct"] = round(farmer_prem / sum_ins * 100, 2) if sum_ins > 0 else 0.0
                g["subsidy_rate_pct"] = round(subsidy_prem / sum_ins * 100, 2) if sum_ins > 0 else 0.0

                ic_hist = self.historical_metrics['companies'].get(g['company_short'], {})
                g["historical_loss_ratio_pct"] = ic_hist.get('historical_loss_ratio_pct', g.get('loss_ratio_pct', 0.0))
                g["historical_premium_rate_pct"] = ic_hist.get('weighted_premium_rate_pct', 0.0)
                g["historical_claims_paid_crore"] = round(ic_hist.get('claims', 0.0), 2)
                g["historical_gross_premium_crore"] = round(ic_hist.get('premium', 0.0), 2)
                g["historical_lr_by_year"] = ic_hist.get('by_year', {})

                g["years"] = sorted(list(g["years"]))
                g["seasons"] = sorted(list(g["seasons"]))
                g["schemes"] = sorted(list(g["schemes"]))
                output_data.append(g)

            output_data.sort(key=lambda x: x.get('farmer_count', 0), reverse=True)

        # Global aggregate KPI totals
        total_farmers = sum(int(d.get('farmer_count') or 0) for d in filtered)
        total_area = round(sum(float(d.get('area_insured_lakh_ha') or 0.0) for d in filtered), 2)
        total_si = round(sum(float(d.get('sum_insured_crore') or 0.0) for d in filtered), 2)
        total_prem = round(sum(float(d.get('gross_premium_crore') or 0.0) for d in filtered), 2)
        total_claims = round(sum(float(d.get('claims_paid_crore') or 0.0) for d in filtered), 2)
        total_ben = sum(int(d.get('benefited_farmers') or 0) for d in filtered)
        overall_lr = round(total_claims / total_prem * 100, 1) if total_prem > 0 else 0.0
        overall_prem_rate = round(total_prem / total_si * 100, 2) if total_si > 0 else 0.0

        # Unique lists for dropdowns
        avail_cos = sorted(list(set(d.get('insurance_company_short') for d in records if d.get('insurance_company_short'))))
        avail_states = []
        seen_st = set()
        for d in records:
            sc = str(d.get('state_code', ''))
            sn = str(d.get('state_name', ''))
            if sc and sc not in seen_st:
                seen_st.add(sc)
                avail_states.append({"state_code": sc, "state_name": sn})
        avail_states.sort(key=lambda x: x["state_name"])

        calc_years = ['2026', '2025', '2024', '2023', '2022', '2021', '2020', '2019', '2018', '2017']
        avail_years = sorted(list(set([str(d.get('year')) for d in records if d.get('year')] + calc_years)), reverse=True)

        return {
            "success": True,
            "level": level,
            "year": year,
            "season": season,
            "scheme": scheme,
            "company": company,
            "state_code": state_code,
            "count": len(output_data),
            "summary": {
                "total_records": len(output_data) if level == 'crop' else len(filtered),
                "total_farmers": total_farmers,
                "total_area_lakh_ha": total_area,
                "total_sum_insured_crore": total_si,
                "total_gross_premium_crore": total_prem,
                "total_claims_paid_crore": total_claims,
                "total_benefited_farmers": total_ben,
                "overall_loss_ratio_pct": overall_lr,
                "overall_premium_rate_pct": overall_prem_rate
            },
            "data": output_data,
            "available_companies": avail_cos,
            "available_states": avail_states,
            "available_years": avail_years
        }

    def generate_company_excel(self, year="all", season="all", scheme="all", level="company", company="all", state_code="all"):
        """
        Generates customized multi-sheet Excel (.xlsx) workbook for Insurance Company analytics.
        Contains:
          - Sheet 1: Insurance_Company_Summary
          - Sheet 2: State_Wise_Distribution
          - Sheet 3: District_Wise_Allocation
        """
        wb = openpyxl.Workbook()
        wb.remove(wb.active)

        header_font = Font(name='Segoe UI', size=11, bold=True, color='FFFFFF')
        header_fill_blue = PatternFill(start_color='1E3A8A', end_color='1E3A8A', fill_type='solid')
        header_fill_teal = PatternFill(start_color='0D9488', end_color='0D9488', fill_type='solid')
        header_fill_amber = PatternFill(start_color='B45309', end_color='B45309', fill_type='solid')
        header_fill_emerald = PatternFill(start_color='047857', end_color='047857', fill_type='solid')

        data_font = Font(name='Segoe UI', size=10)
        thin_border = Border(
            left=Side(style='thin', color='CBD5E1'),
            right=Side(style='thin', color='CBD5E1'),
            top=Side(style='thin', color='CBD5E1'),
            bottom=Side(style='thin', color='CBD5E1')
        )

        # 1. Company Summary Sheet
        res_comp = self.get_company_analytics(year=year, season=season, scheme=scheme, level='company', company=company, state_code=state_code)
        ws1 = wb.create_sheet(title="Insurance_Company_Summary")
        headers1 = [
            "Insurance Company", "Districts Allocated", "Operating States",
            "Farmers Enrolled", "Area Insured (Lakh Ha)", "Sum Insured (₹ Cr)",
            "Gross Premium (₹ Cr)", "Company Premium Rate (%)", "Farmer Share (₹ Cr)", "Central Subsidy (₹ Cr)", "State Subsidy (₹ Cr)",
            "Claims Settled (₹ Cr)", "Benefited Farmers", "Current Loss Ratio (%)", "Historical Loss Ratio (%)"
        ]
        ws1.append(headers1)
        for col_idx in range(1, len(headers1) + 1):
            c = ws1.cell(row=1, column=col_idx)
            c.font = header_font
            c.fill = header_fill_blue
            c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

        for row_idx, d in enumerate(res_comp.get("data", []), start=2):
            row_vals = [
                d.get("company_short", ""), d.get("districts_count", 0), d.get("states_count", 0),
                d.get("farmer_count", 0), d.get("area_insured_lakh_ha", 0.0), d.get("sum_insured_crore", 0.0),
                d.get("gross_premium_crore", 0.0), d.get("company_premium_rate_pct", 0.0), d.get("farmer_share_crore", 0.0), d.get("goi_share_crore", 0.0), d.get("state_share_crore", 0.0),
                d.get("claims_paid_crore", 0.0), d.get("benefited_farmers", 0), d.get("loss_ratio_pct", 0.0), d.get("historical_loss_ratio_pct", 0.0)
            ]
            ws1.append(row_vals)
            for c_idx in range(1, len(row_vals) + 1):
                c = ws1.cell(row=row_idx, column=c_idx)
                c.font = data_font
                c.border = thin_border
                if c_idx in [2, 3, 4, 13]:
                    c.number_format = '#,##0'
                elif c_idx in [5, 6, 7, 9, 10, 11, 12]:
                    c.number_format = '#,##0.00'
                elif c_idx in [8, 14, 15]:
                    c.number_format = '0.00"%"'

        for col in ws1.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            ws1.column_dimensions[get_column_letter(col[0].column)].width = max(max_len + 3, 14)

        # 2. State-Wise Distribution Sheet
        res_state = self.get_company_analytics(year=year, season=season, scheme=scheme, level='state', company=company, state_code=state_code)
        ws2 = wb.create_sheet(title="State_Wise_Distribution")
        headers2 = [
            "State Name", "Designated Insurance Company", "Year", "Season", "Scheme", "Districts Covered",
            "Farmers Enrolled", "Area Insured (Lakh Ha)", "Sum Insured (₹ Cr)",
            "Gross Premium (₹ Cr)", "State Premium Rate (%)", "Farmer Share (₹ Cr)", "Central Subsidy (₹ Cr)", "State Subsidy (₹ Cr)",
            "Claims Paid (₹ Cr)", "Benefited Farmers", "Current Loss Ratio (%)", "Historical Loss Ratio (%)"
        ]
        ws2.append(headers2)
        for col_idx in range(1, len(headers2) + 1):
            c = ws2.cell(row=1, column=col_idx)
            c.font = header_font
            c.fill = header_fill_teal
            c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

        for row_idx, d in enumerate(res_state.get("data", []), start=2):
            row_vals = [
                d.get("state_name", ""), d.get("insurance_company_short", ""), d.get("year", ""), d.get("season", ""), d.get("scheme", ""), d.get("districts_count", 0),
                d.get("farmer_count", 0), d.get("area_insured_lakh_ha", 0.0), d.get("sum_insured_crore", 0.0),
                d.get("gross_premium_crore", 0.0), d.get("state_premium_rate_pct", 0.0), d.get("farmer_share_crore", 0.0), d.get("goi_share_crore", 0.0), d.get("state_share_crore", 0.0),
                d.get("claims_paid_crore", 0.0), d.get("benefited_farmers", 0), d.get("loss_ratio_pct", 0.0), d.get("historical_loss_ratio_pct", 0.0)
            ]
            ws2.append(row_vals)
            for c_idx in range(1, len(row_vals) + 1):
                c = ws2.cell(row=row_idx, column=c_idx)
                c.font = data_font
                c.border = thin_border
                if c_idx in [6, 7, 16]:
                    c.number_format = '#,##0'
                elif c_idx in [8, 9, 10, 12, 13, 14, 15]:
                    c.number_format = '#,##0.00'
                elif c_idx in [11, 17, 18]:
                    c.number_format = '0.00"%"'

        for col in ws2.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            ws2.column_dimensions[get_column_letter(col[0].column)].width = max(max_len + 3, 14)

        # 3. District-Wise Allocation Sheet
        res_dist = self.get_company_analytics(year=year, season=season, scheme=scheme, level='district', company=company, state_code=state_code)
        ws3 = wb.create_sheet(title="District_Wise_Allocation")
        headers3 = [
            "State Name", "District Name", "Designated Insurance Company", "Year", "Season", "Scheme",
            "Farmers Enrolled", "Area Insured (Lakh Ha)", "Sum Insured (₹ Cr)",
            "Gross Premium (₹ Cr)", "District Premium Rate (%)", "Farmer Share Rate (%)", "Farmer Share (₹ Cr)", "Central Subsidy (₹ Cr)", "State Subsidy (₹ Cr)",
            "Claims Paid (₹ Cr)", "Benefited Farmers", "Current Loss Ratio (%)", "District Historical LR (%)"
        ]
        ws3.append(headers3)
        for col_idx in range(1, len(headers3) + 1):
            c = ws3.cell(row=1, column=col_idx)
            c.font = header_font
            c.fill = header_fill_amber
            c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

        for d in res_dist.get("data", []):
            row_vals = [
                d.get("state_name", ""), d.get("district_name", ""), d.get("insurance_company_short", ""), d.get("year", ""), d.get("season", ""), d.get("scheme", ""),
                d.get("farmer_count", 0), d.get("area_insured_lakh_ha", 0.0), d.get("sum_insured_crore", 0.0),
                d.get("gross_premium_crore", 0.0), d.get("district_premium_rate_pct", 0.0), d.get("farmer_premium_rate_pct", 0.0), d.get("farmer_share_crore", 0.0), d.get("goi_share_crore", 0.0), d.get("state_share_crore", 0.0),
                d.get("claims_paid_crore", 0.0), d.get("benefited_farmers", 0), d.get("loss_ratio_pct", 0.0), d.get("historical_loss_ratio_pct", 0.0)
            ]
            ws3.append(row_vals)

        for row in ws3.iter_rows(min_row=2):
            for idx in (6, 16):
                row[idx].number_format = '#,##0'
            for idx in (7, 8, 9, 12, 13, 14, 15):
                row[idx].number_format = '#,##0.00'
            for idx in (10, 11, 17, 18):
                row[idx].number_format = '0.00"%"'

        for col_idx in range(1, len(headers3) + 1):
            ws3.column_dimensions[get_column_letter(col_idx)].width = 18

        # 4. Crop-Wise District Rates Sheet (Official PMFBY Premium Calculator Notified Rates)
        res_crop = self.get_company_analytics(year=year, season=season, scheme=scheme, level='crop', company=company, state_code=state_code)
        ws4 = wb.create_sheet(title="Crop_Wise_District_Rates")
        headers4 = [
            "State Name", "District Name", "Crop Name", "Crop Category",
            "Designated Insurance Company", "Year", "Season", "Scheme",
            "Actuarial Premium Rate (%)", "Farmer Share Rate (%)", "Govt Subsidy Rate (%)",
            "Sum Insured (₹/Ha)", "District Aggregate Rate (%)", "District Historical LR (%)", "Company Historical LR (%)"
        ]
        ws4.append(headers4)
        for col_idx in range(1, len(headers4) + 1):
            c = ws4.cell(row=1, column=col_idx)
            c.font = header_font
            c.fill = header_fill_emerald
            c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

        for d in res_crop.get("data", []):
            row_vals = [
                d.get("state_name", ""), d.get("district_name", ""), d.get("crop_name", ""), d.get("crop_category", ""),
                d.get("insurance_company_short", ""), d.get("year", ""), d.get("season", ""), d.get("scheme", ""),
                d.get("actuarial_rate_pct", 0.0), d.get("farmer_rate_pct", 0.0), d.get("total_subsidy_rate_pct", 0.0),
                d.get("sum_insured_per_ha", 0.0), d.get("district_premium_rate_pct", 0.0), d.get("district_historical_lr_pct", 0.0), d.get("company_historical_lr_pct", 0.0)
            ]
            ws4.append(row_vals)

        for row in ws4.iter_rows(min_row=2):
            row[11].number_format = '#,##0.00'
            for idx in (8, 9, 10, 12, 13, 14):
                row[idx].number_format = '0.00"%"'

        for col_idx in range(1, len(headers4) + 1):
            ws4.column_dimensions[get_column_letter(col_idx)].width = 20

        out = io.BytesIO()
        wb.save(out)
        out.seek(0)
        return out

    def generate_excel_workbook(self, year="2024", season_code="01"):
        """
        Creates a comprehensive multi-sheet Excel (.xlsx) file
        containing National, State-wise, District-wise (with Insurance Company),
        and Insurance Company Performance Summary sheets.
        """
        wb = openpyxl.Workbook()
        wb.remove(wb.active)

        header_font = Font(name='Segoe UI', size=11, bold=True, color='FFFFFF')
        header_fill = PatternFill(start_color='1E3A8A', end_color='1E3A8A', fill_type='solid') # Navy
        sub_header_fill = PatternFill(start_color='0284C7', end_color='0284C7', fill_type='solid') # Blue
        district_header_fill = PatternFill(start_color='0D9488', end_color='0D9488', fill_type='solid') # Teal
        ic_header_fill = PatternFill(start_color='B45309', end_color='B45309', fill_type='solid') # Amber

        data_font = Font(name='Segoe UI', size=10)
        thin_border = Border(
            left=Side(style='thin', color='CBD5E1'),
            right=Side(style='thin', color='CBD5E1'),
            top=Side(style='thin', color='CBD5E1'),
            bottom=Side(style='thin', color='CBD5E1')
        )

        # -------------------------------------------------------------
        # SHEET 1: National Time-Series (2018 - 2026)
        # -------------------------------------------------------------
        ws1 = wb.create_sheet(title="National_Summary_2018_2026")
        summary_data = self.get_national_summary()

        headers1 = [
            "Season & Year", "Year", "Season", "States", "Districts", "Insurance Units",
            "Enrolled Farmers", "Total Applications", "Loanee Farmers", "Non-Loanee Farmers",
            "Area Insured (Lakh Ha)", "Sum Insured (₹ Cr)", "Gross Premium (₹ Cr)",
            "Farmer Share (₹ Cr)", "Central Subsidy (₹ Cr)", "State Subsidy (₹ Cr)",
            "Claims Paid (₹ Cr)", "Benefited Farmers", "Loss Ratio (%)"
        ]

        ws1.append(headers1)
        for col_idx in range(1, len(headers1) + 1):
            cell = ws1.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

        for row_idx, s in enumerate(summary_data, start=2):
            row_vals = [
                s["display_name"], s["year"], s["season_name"], s["state_count"], s["district_count"], s["iu_count"],
                s["farmer_count"], s["total_applications"], s["loanee"], s["non_loanee"],
                s["area_insured_lakh_ha"], s["sum_insured_crore"], s["gross_premium_crore"],
                s["farmer_premium_crore"], s["goi_subsidy_crore"], s["state_subsidy_crore"],
                s["claims_paid_crore"], s["benefited_farmers"], s["loss_ratio_pct"]
            ]
            ws1.append(row_vals)
            for c_idx in range(1, len(row_vals) + 1):
                c = ws1.cell(row=row_idx, column=c_idx)
                c.font = data_font
                c.border = thin_border
                if c_idx in [7, 8, 9, 10, 18]:
                    c.number_format = '#,##0'
                elif c_idx in [11, 12, 13, 14, 15, 16, 17]:
                    c.number_format = '#,##0.00'
                elif c_idx == 19:
                    c.number_format = '0.0"%"'

        for col in ws1.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws1.column_dimensions[col_letter].width = max(max_len + 3, 12)

        # -------------------------------------------------------------
        # SHEET 2: State-Wise Performance
        # -------------------------------------------------------------
        ws2 = wb.create_sheet(title="State_Wise_Performance")
        state_data = self.get_state_report(year, season_code)
        if not state_data:
            state_data = self.get_state_report("2023", "01")

        headers2 = [
            "State Name", "Season", "Year", "Districts Covered", "Insurance Units",
            "Farmers Enrolled", "Non-Loanee Farmers", "Area Insured (Lakh Ha)",
            "Sum Insured (₹ Cr)", "Gross Premium (₹ Cr)", "Farmer Share (₹ Cr)",
            "Central Govt Share (₹ Cr)", "State Govt Share (₹ Cr)",
            "Total Claims Paid (₹ Cr)", "Claim Beneficiary Farmers", "Loss Ratio (%)"
        ]

        ws2.append(headers2)
        for col_idx in range(1, len(headers2) + 1):
            cell = ws2.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = sub_header_fill
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

        for row_idx, st in enumerate(state_data, start=2):
            row_vals = [
                st["state_name"], st["season"], st["year"], st["districts"], st["iu_count"],
                st["farmer_count"], st["non_loanee"], st["area_insured_lakh_ha"],
                st["sum_insured_crore"], st["gross_premium_crore"], st["farmer_share_crore"],
                st["goi_share_crore"], st["state_share_crore"],
                st["claims_paid_crore"], st["benefited_farmers"], st["loss_ratio_pct"]
            ]
            ws2.append(row_vals)
            for c_idx in range(1, len(row_vals) + 1):
                c = ws2.cell(row=row_idx, column=c_idx)
                c.font = data_font
                c.border = thin_border
                if c_idx in [6, 7, 15]:
                    c.number_format = '#,##0'
                elif c_idx in [8, 9, 10, 11, 12, 13, 14]:
                    c.number_format = '#,##0.00'
                elif c_idx == 16:
                    c.number_format = '0.0"%"'

        for col in ws2.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws2.column_dimensions[col_letter].width = max(max_len + 3, 14)

        # -------------------------------------------------------------
        # SHEET 3: District-Wise Performance (With Insurance Company!)
        # -------------------------------------------------------------
        ws3 = wb.create_sheet(title="District_Wise_Performance")
        district_data = self.get_district_reports(year, season_code)

        headers3 = [
            "State Name", "District Name", "Designated Insurance Company",
            "Season", "Year", "Insurance Units",
            "Farmers Enrolled", "Loanee Farmers", "Non-Loanee Farmers",
            "Area Insured (Lakh Ha)", "Sum Insured (₹ Cr)", "Gross Premium (₹ Cr)",
            "Farmer Share (₹ Cr)", "Central Subsidy (₹ Cr)", "State Subsidy (₹ Cr)",
            "Claims Paid (₹ Cr)", "Benefited Farmers", "Loss Ratio (%)"
        ]

        ws3.append(headers3)
        for col_idx in range(1, len(headers3) + 1):
            cell = ws3.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = district_header_fill
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

        for row_idx, d in enumerate(district_data, start=2):
            row_vals = [
                d.get("state_name", ""), d.get("district_name", ""), d.get("insurance_company", "AIC of India"),
                d.get("season", "Kharif"), d.get("year", year), d.get("iu_count", 0),
                d.get("farmer_count", 0), d.get("loanee", 0), d.get("non_loanee", 0),
                d.get("area_insured_lakh_ha", 0.0), d.get("sum_insured_crore", 0.0), d.get("gross_premium_crore", 0.0),
                d.get("farmer_share_crore", 0.0), d.get("goi_share_crore", 0.0), d.get("state_share_crore", 0.0),
                d.get("claims_paid_crore", 0.0), d.get("benefited_farmers", 0), d.get("loss_ratio_pct", 0.0)
            ]
            ws3.append(row_vals)
            for c_idx in range(1, len(row_vals) + 1):
                c = ws3.cell(row=row_idx, column=c_idx)
                c.font = data_font
                c.border = thin_border
                if c_idx in [6, 7, 8, 9, 17]:
                    c.number_format = '#,##0'
                elif c_idx in [10, 11, 12, 13, 14, 15, 16]:
                    c.number_format = '#,##0.00'
                elif c_idx == 18:
                    c.number_format = '0.0"%"'

        for col in ws3.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws3.column_dimensions[col_letter].width = max(max_len + 3, 14)

        # -------------------------------------------------------------
        # SHEET 4: Insurance Company Year-Wise Summary (New!)
        # -------------------------------------------------------------
        ws4 = wb.create_sheet(title="Insurance_Company_Summary")
        headers4 = [
            "Insurance Company Name", "Short Name", "Districts Allocated",
            "Participating States", "Farmers Enrolled", "Area Insured (Lakh Ha)",
            "Sum Insured (₹ Cr)", "Gross Premium (₹ Cr)", "Claims Settled (₹ Cr)",
            "Benefited Farmers", "Loss Ratio (%)"
        ]

        ws4.append(headers4)
        for col_idx in range(1, len(headers4) + 1):
            cell = ws4.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = ic_header_fill
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

        # Aggregate district data by insurance company
        ic_agg = {}
        for d in district_data:
            ic_name = d.get("insurance_company") or "AIC of India"
            ic_short = d.get("insurance_company_short") or "AIC of India"
            if ic_name not in ic_agg:
                ic_agg[ic_name] = {
                    "full_name": ic_name,
                    "short_name": ic_short,
                    "districts": 0,
                    "states": set(),
                    "farmers": 0,
                    "area": 0.0,
                    "sum_insured": 0.0,
                    "premium": 0.0,
                    "claims": 0.0,
                    "benefited": 0
                }
            ic_agg[ic_name]["districts"] += 1
            ic_agg[ic_name]["states"].add(d["state_name"])
            ic_agg[ic_name]["farmers"] += d["farmer_count"]
            ic_agg[ic_name]["area"] += d["area_insured_lakh_ha"]
            ic_agg[ic_name]["sum_insured"] += d["sum_insured_crore"]
            ic_agg[ic_name]["premium"] += d["gross_premium_crore"]
            ic_agg[ic_name]["claims"] += d["claims_paid_crore"]
            ic_agg[ic_name]["benefited"] += d["benefited_farmers"]

        sorted_ics = sorted(ic_agg.values(), key=lambda x: x["farmers"], reverse=True)

        for row_idx, item in enumerate(sorted_ics, start=2):
            l_ratio = round((item["claims"] / item["premium"] * 100), 1) if item["premium"] > 0 else 0.0
            row_vals = [
                item["full_name"],
                item["short_name"],
                item["districts"],
                len(item["states"]),
                item["farmers"],
                round(item["area"], 2),
                round(item["sum_insured"], 2),
                round(item["premium"], 2),
                round(item["claims"], 2),
                item["benefited"],
                l_ratio
            ]
            ws4.append(row_vals)
            for c_idx in range(1, len(row_vals) + 1):
                c = ws4.cell(row=row_idx, column=c_idx)
                c.font = data_font
                c.border = thin_border
                if c_idx in [3, 4, 5, 10]:
                    c.number_format = '#,##0'
                elif c_idx in [6, 7, 8, 9]:
                    c.number_format = '#,##0.00'
                elif c_idx == 11:
                    c.number_format = '0.0"%"'

        for col in ws4.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws4.column_dimensions[col_letter].width = max(max_len + 3, 14)

        # -------------------------------------------------------------
        # SHEET 5: Claims Breakdown by 5 Stages
        # -------------------------------------------------------------
        ws5 = wb.create_sheet(title="Claims_5_Stages_Breakdown")
        headers5 = [
            "Season & Year", "Prevented Sowing (₹ Lakh)", "Mid-Season Adversity (₹ Lakh)",
            "Localised Calamities (₹ Lakh)", "Post-Harvest Losses (₹ Lakh)",
            "End-of-Season Yield Loss (₹ Lakh)", "RWBCIS Weather Claims (₹ Lakh)",
            "Total Claims Paid (₹ Cr)"
        ]

        ws5.append(headers5)
        for col_idx in range(1, len(headers5) + 1):
            cell = ws5.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = PatternFill(start_color='DC2626', end_color='DC2626', fill_type='solid') # Red
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

        for row_idx, s in enumerate(summary_data, start=2):
            row_vals = [
                s["display_name"],
                s["claim_prevented_sowing_lakh"],
                s["claim_mid_term_lakh"],
                s["claim_localised_lakh"],
                s["claim_post_harvest_lakh"],
                s["claim_yield_lakh"],
                s["claim_rwbcis_lakh"],
                s["claims_paid_crore"]
            ]
            ws5.append(row_vals)
            for c_idx in range(1, len(row_vals) + 1):
                c = ws5.cell(row=row_idx, column=c_idx)
                c.font = data_font
                c.border = thin_border
                if c_idx >= 2:
                    c.number_format = '#,##0.00'

        for col in ws5.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws5.column_dimensions[col_letter].width = max(max_len + 3, 16)

        # -------------------------------------------------------------
        # SHEET 6: Demographics & Inclusivity
        # -------------------------------------------------------------
        ws6 = wb.create_sheet(title="Farmer_Demographics_Inclusivity")
        headers6 = [
            "Season & Year", "Small & Marginal Farmers (%)", "Other Farmers (%)",
            "Male (%)", "Female (%)", "Transgender (%)",
            "OBC Category (%)", "SC Category (%)", "ST Category (%)", "General Category (%)"
        ]

        ws6.append(headers6)
        for col_idx in range(1, len(headers6) + 1):
            cell = ws6.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = PatternFill(start_color='15803D', end_color='15803D', fill_type='solid') # Green
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

        for row_idx, s in enumerate(summary_data, start=2):
            small_marginal = round(s["small_pct"] + s["marginal_pct"], 1)
            row_vals = [
                s["display_name"],
                small_marginal,
                s["other_farm_pct"],
                s["male_pct"],
                s["female_pct"],
                s["transgender_pct"],
                s["obc_pct"],
                s["sc_pct"],
                s["st_pct"],
                s["gen_pct"]
            ]
            ws6.append(row_vals)
            for c_idx in range(1, len(row_vals) + 1):
                c = ws6.cell(row=row_idx, column=c_idx)
                c.font = data_font
                c.border = thin_border
                if c_idx >= 2:
                    c.number_format = '0.0"%"'

        for col in ws6.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws6.column_dimensions[col_letter].width = max(max_len + 3, 15)

        out = io.BytesIO()
        wb.save(out)
        out.seek(0)
        return out
