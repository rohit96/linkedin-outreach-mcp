"""Pipeline data management.

Stores prospects in a JSON file with the following status flow:
  Discovered → Ready (has note) → Sent → Accepted → Follow-up Sent

Each prospect record:
{
    "name": "Jane Doe",
    "title": "VP Marketing at Acme",
    "company": "Acme Corp",
    "location": "London, UK",
    "linkedin_url": "https://www.linkedin.com/in/janedoe/",
    "status": "Discovered",
    "region": "london",
    "connection_note": "",
    "followup_message": "",
    "sent_at": null,
    "accepted_at": null,
    "followup_at": null,
    "source": "search"
}
"""

import csv
import io
import json
import os
from collections import Counter
from datetime import datetime

from . import config


def _pipeline_path() -> str:
    return config.PIPELINE_PATH


def load() -> list[dict]:
    """Load the prospect pipeline from disk."""
    path = _pipeline_path()
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)


def save(prospects: list[dict]):
    """Save the prospect pipeline to disk."""
    config.ensure_data_dir()
    with open(_pipeline_path(), "w") as f:
        json.dump(prospects, f, indent=2, ensure_ascii=False)


def _extract_public_id(url: str) -> str:
    """Extract the LinkedIn public ID from a profile URL."""
    if "/in/" not in url:
        return ""
    return url.rstrip("/").split("/in/")[-1].split("?")[0].lower()


def add_prospects(new_prospects: list[dict]) -> dict:
    """Add prospects to the pipeline, deduplicating by LinkedIn URL.

    Returns: {"added": int, "duplicates": int, "total": int}
    """
    existing = load()

    existing_pids = set()
    for p in existing:
        url = p.get("linkedin_url", "")
        if url:
            existing_pids.add(_extract_public_id(url))

    added = 0
    duplicates = 0

    for prospect in new_prospects:
        url = prospect.get("linkedin_url", "")
        pid = _extract_public_id(url) if url else ""

        if pid and pid in existing_pids:
            duplicates += 1
            continue

        # Ensure required fields
        record = {
            "name": prospect.get("name", ""),
            "title": prospect.get("title", ""),
            "company": prospect.get("company", ""),
            "location": prospect.get("location", ""),
            "linkedin_url": url,
            "status": "Discovered",
            "region": prospect.get("region", ""),
            "connection_note": prospect.get("connection_note", ""),
            "followup_message": "",
            "sent_at": None,
            "accepted_at": None,
            "followup_at": None,
            "source": prospect.get("source", "import"),
        }
        existing.append(record)
        if pid:
            existing_pids.add(pid)
        added += 1

    save(existing)
    return {"added": added, "duplicates": duplicates, "total": len(existing)}


def get_prospects(
    status: str | None = None,
    region: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Get prospects with optional filters."""
    prospects = load()

    if status:
        prospects = [p for p in prospects if p.get("status", "").lower() == status.lower()]
    if region:
        prospects = [p for p in prospects if p.get("region", "").lower() == region.lower()]
    if limit:
        prospects = prospects[:limit]

    return prospects


def update_prospect(linkedin_url: str, **fields) -> dict | None:
    """Update a prospect by LinkedIn URL. Returns the updated prospect or None."""
    prospects = load()
    pid = _extract_public_id(linkedin_url)

    for p in prospects:
        p_pid = _extract_public_id(p.get("linkedin_url", ""))
        if p_pid == pid:
            p.update(fields)
            save(prospects)
            return p

    return None


def bulk_update_notes(notes: list[dict]) -> int:
    """Save connection notes for multiple prospects.

    notes: [{"linkedin_url": "...", "connection_note": "..."}, ...]
    Returns: number of prospects updated.
    """
    prospects = load()
    pid_to_note = {}
    for n in notes:
        pid = _extract_public_id(n.get("linkedin_url", ""))
        if pid:
            pid_to_note[pid] = n.get("connection_note", "")

    updated = 0
    for p in prospects:
        p_pid = _extract_public_id(p.get("linkedin_url", ""))
        if p_pid in pid_to_note:
            p["connection_note"] = pid_to_note[p_pid]
            if p["status"] == "Discovered":
                p["status"] = "Ready"
            updated += 1

    save(prospects)
    return updated


def mark_sent(linkedin_url: str, success: bool, error: str = ""):
    """Mark a prospect as sent or failed."""
    now = datetime.now().isoformat()
    if success:
        update_prospect(linkedin_url, status="Sent", sent_at=now)
    else:
        update_prospect(linkedin_url, status=f"Failed: {error}", sent_at=now)


def mark_accepted(linkedin_url: str):
    """Mark a prospect as accepted."""
    update_prospect(
        linkedin_url,
        status="Accepted",
        accepted="Yes",
        accepted_at=datetime.now().isoformat(),
    )


def mark_followup_sent(linkedin_url: str):
    """Mark a follow-up as sent."""
    update_prospect(
        linkedin_url,
        status="Follow-up Sent",
        followup_sent="Yes",
        followup_at=datetime.now().isoformat(),
    )


def get_summary() -> dict:
    """Get pipeline summary with counts by status."""
    prospects = load()
    status_counts = Counter(p.get("status", "Unknown") for p in prospects)
    region_counts = Counter(p.get("region", "Unknown") for p in prospects)

    return {
        "total": len(prospects),
        "by_status": dict(status_counts),
        "by_region": dict(region_counts),
    }


def get_prospects_needing_notes(limit: int | None = None) -> list[dict]:
    """Get prospects that don't have connection notes yet."""
    prospects = load()
    needing = [
        p for p in prospects
        if p.get("status") == "Discovered" and not p.get("connection_note")
    ]
    if limit:
        needing = needing[:limit]
    return needing


def export_csv() -> str:
    """Export pipeline to CSV format. Returns CSV string."""
    prospects = load()
    if not prospects:
        return "No prospects in pipeline."

    output = io.StringIO()
    fields = [
        "name", "title", "company", "location", "linkedin_url",
        "status", "region", "connection_note", "sent_at", "accepted_at",
        "followup_message", "followup_at", "source",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for p in prospects:
        writer.writerow(p)

    return output.getvalue()
