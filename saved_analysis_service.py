"""
Saved Analysis Service for PMFBY Pricing Dashboard
===================================================
Manages saving, retrieving, listing, and deleting actuarial pricing reviews,
threshold yield evaluations, cluster matrices, and bidding simulations.
"""

import os
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

SAVED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "saved_analyses")
INDEX_PATH = os.path.join(SAVED_DIR, "index.json")

def _ensure_dir():
    if not os.path.exists(SAVED_DIR):
        os.makedirs(SAVED_DIR, exist_ok=True)
    if not os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)

class SavedAnalysisService:
    @staticmethod
    def list_all() -> List[Dict[str, Any]]:
        """Returns metadata list of all saved analyses sorted by most recent first."""
        _ensure_dir()
        try:
            with open(INDEX_PATH, "r", encoding="utf-8") as f:
                items = json.load(f)
            return sorted(items, key=lambda x: x.get("created_at_iso", ""), reverse=True)
        except Exception:
            return []

    @staticmethod
    def save(name: str, payload: Dict[str, Any], notes: str = "") -> Dict[str, Any]:
        """Saves a complete actuarial analysis payload to disk and updates index."""
        _ensure_dir()
        analysis_id = str(uuid.uuid4())[:12]
        now = datetime.now()
        created_at_iso = now.isoformat()
        created_at_display = now.strftime("%d %b %Y, %I:%M %p")

        review_data = payload.get("review") or payload
        ty = review_data.get("threshold_yield_analysis") or {}
        summary = review_data.get("summary") or {}

        # Build clean title if not provided
        file_list = review_data.get("uploaded_filenames") or ([review_data.get("filename")] if review_data.get("filename") else ["Portfolio_Review"])
        if not name or not name.strip():
            m = (payload.get("currentTYMethod") or ty.get("active_method") or "5b7").upper()
            il = payload.get("currentIndemnityLevel") or ty.get("active_indemnity_pct") or 80
            name = f"PMFBY Analysis - {file_list[0]} ({m} @ {il}%)"

        meta = {
            "id": analysis_id,
            "name": name.strip(),
            "notes": notes.strip(),
            "created_at_iso": created_at_iso,
            "created_at": created_at_display,
            "source_files": file_list,
            "states_list": review_data.get("states_list") or [],
            "total_units": ty.get("total_units") or review_data.get("total_rows") or 0,
            "total_sum_insured_display": summary.get("total_sum_insured_display") or "₹0.0 Cr",
            "portfolio_bc_pct": ty.get("portfolio_burning_cost_pct") or 0.0,
            "active_method": (payload.get("currentTYMethod") or ty.get("active_method") or "5b7").upper(),
            "active_indemnity_pct": payload.get("currentIndemnityLevel") or ty.get("active_indemnity_pct") or 80,
            "clusters_count": len(ty.get("cluster_wise_analysis") or []),
            "crops_count": len(ty.get("crop_wise_analysis") or [])
        }

        # Save complete data to dedicated JSON file
        file_path = os.path.join(SAVED_DIR, f"{analysis_id}.json")
        complete_record = {
            "metadata": meta,
            "payload": payload
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(complete_record, f, indent=2)

        # Update index
        items = SavedAnalysisService.list_all()
        items.insert(0, meta)
        with open(INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2)

        return meta

    @staticmethod
    def get(analysis_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves complete analysis record by ID."""
        _ensure_dir()
        file_path = os.path.join(SAVED_DIR, f"{analysis_id}.json")
        if not os.path.exists(file_path):
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    @staticmethod
    def delete(analysis_id: str) -> bool:
        """Deletes an analysis file and removes it from index."""
        _ensure_dir()
        file_path = os.path.join(SAVED_DIR, f"{analysis_id}.json")
        deleted = False
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                deleted = True
            except OSError:
                pass

        # Update index
        try:
            items = SavedAnalysisService.list_all()
            new_items = [it for it in items if it.get("id") != analysis_id]
            with open(INDEX_PATH, "w", encoding="utf-8") as f:
                json.dump(new_items, f, indent=2)
            return deleted or len(new_items) < len(items)
        except Exception:
            return deleted
