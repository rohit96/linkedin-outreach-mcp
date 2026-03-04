"""LinkedIn Outreach MCP Server.

Exposes tools for the full LinkedIn outreach pipeline:
  1. Login & Setup — authenticate and configure your profile
  2. Lead Import — add prospects from LinkedIn URLs
  3. Lead Search — find prospects by title, location, industry
  4. Personalization — save AI-generated connection notes
  5. Outreach — send connection requests
  6. Tracking — check acceptances, send follow-ups
  7. Reporting — view pipeline status, export data

Install in Claude Code:
  claude mcp add linkedin-outreach -- python -m linkedin_outreach_mcp
"""

import asyncio
import json
import logging
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from . import config, pipeline, search, personalize
from .browser import (
    launch_browser,
    verify_login,
    do_login,
    send_connection_request,
    check_acceptances_on_page,
    send_followup_message,
    read_conversation,
)

log = logging.getLogger(__name__)

mcp = FastMCP(
    "linkedin-outreach",
    instructions="""LinkedIn Outreach MCP Server — automates LinkedIn networking.

WORKFLOW: When a user wants to do LinkedIn outreach, guide them through these steps:

1. SETUP (first time only):
   - Call `linkedin_login` to authenticate
   - Call `setup_profile` with their professional info

2. ADD LEADS (one of):
   a) `import_leads` — if user has LinkedIn URLs ready
   b) `search_leads` — if user wants to find prospects by criteria
      Ask them: target titles, locations, number of leads

3. PERSONALIZE:
   - Call `get_prospects` with status="Discovered" to see leads needing notes
   - Generate a personalized 300-char connection note for each prospect
     using their title/company/location and the user's profile
   - Call `save_notes` to save the generated notes

4. SEND:
   - Call `send_connections` with a limit and dry_run=true first to preview
   - Then send for real with dry_run=false

5. TRACK:
   - Call `check_acceptances` to see who accepted
   - Call `send_followups` for accepted connections
   - Call `view_pipeline` anytime for status overview

IMPORTANT:
- Always confirm with the user before sending real connections
- Default to dry_run=true for first attempt
- Respect daily limits (default: 20 connections/day, 30 messages/day)
- Connection notes must be ≤300 characters
- Follow-up messages should be ≤500 characters
""",
)


# ── Helper: run sync browser code in thread ──────────────────────


def _run_sync(func, *args, **kwargs):
    """Run a sync function in a thread to avoid blocking the async event loop."""
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(func, *args, **kwargs)
        return future.result(timeout=300)


# ── Tool 1: Login ────────────────────────────────────────────────


@mcp.tool()
def linkedin_login() -> str:
    """Open a browser window for LinkedIn login.

    A browser will open — log in to LinkedIn manually.
    The session is saved for future use.
    Call this before any other tool if not logged in.
    """
    from playwright.sync_api import sync_playwright

    def _do_login():
        with sync_playwright() as pw:
            context, page = launch_browser(pw)
            try:
                if verify_login(page):
                    return "Already logged in to LinkedIn. Session is valid."

                success = do_login(page)
                if success:
                    return (
                        "Successfully logged in to LinkedIn! "
                        "Session saved for future use."
                    )
                else:
                    return (
                        "Login timed out. Please try again — "
                        "a browser window will open for you to log in."
                    )
            finally:
                context.close()

    return _run_sync(_do_login)


# ── Tool 2: Setup Profile ───────────────────────────────────────


@mcp.tool()
def setup_profile(
    name: str,
    headline: str,
    current_title: str = "",
    current_company: str = "",
    location: str = "",
    summary: str = "",
    skills: list[str] | None = None,
    industries: list[str] | None = None,
    networking_goal: str = "",
) -> str:
    """Save your professional profile for personalized outreach messages.

    Call this on first setup. The profile is used to craft connection notes
    that reference your background and create relevant common ground.

    Args:
        name: Your first name (used in message signatures).
        headline: Your professional headline (e.g. "Growth Marketing Leader").
        current_title: Current job title.
        current_company: Current company name.
        location: Your location.
        summary: Brief professional summary (2-3 sentences).
        skills: List of key skills.
        industries: List of industries you work in.
        networking_goal: What you're looking to achieve (e.g. "Exploring roles in London tech scene").
    """
    profile = {
        "name": name,
        "headline": headline,
        "current_role": {
            "title": current_title,
            "company": current_company,
        },
        "location": location,
        "summary": summary,
        "skills": skills or [],
        "industries": industries or [],
        "networking_goal": networking_goal,
    }
    config.save_profile(profile)
    return f"Profile saved for {name}. You're ready to start outreach!"


# ── Tool 3: Get Profile ─────────────────────────────────────────


@mcp.tool()
def get_profile() -> str:
    """Get the current user profile used for personalization.

    Returns the saved profile or a message if not set up yet.
    """
    profile = config.load_profile()
    if not profile:
        return (
            "No profile set up yet. Call setup_profile first with your "
            "name, headline, and professional details."
        )
    return json.dumps(profile, indent=2)


# ── Tool 4: Update Config ───────────────────────────────────────


@mcp.tool()
def update_config(
    daily_connection_limit: int | None = None,
    daily_message_limit: int | None = None,
    delay_between_actions: int | None = None,
    delay_between_prospects: int | None = None,
) -> str:
    """Update outreach configuration settings.

    Args:
        daily_connection_limit: Max connection requests per day (default: 20).
        daily_message_limit: Max messages per day (default: 30).
        delay_between_actions: Seconds between actions (default: 2).
        delay_between_prospects: Seconds between prospects (default: 5).
    """
    cfg = config.load_config()

    if daily_connection_limit is not None:
        cfg["daily_limits"]["connection_requests"] = daily_connection_limit
    if daily_message_limit is not None:
        cfg["daily_limits"]["messages"] = daily_message_limit
    if delay_between_actions is not None:
        cfg["delays"]["between_actions"] = delay_between_actions
    if delay_between_prospects is not None:
        cfg["delays"]["between_prospects"] = delay_between_prospects

    config.save_config(cfg)
    return f"Config updated:\n{json.dumps(cfg, indent=2)}"


# ── Tool 5: Import Leads ────────────────────────────────────────


@mcp.tool()
def import_leads(leads: list[dict]) -> str:
    """Import prospects into the pipeline from a list of LinkedIn URLs.

    Each lead should have at minimum a `linkedin_url`. Optionally include
    `name`, `title`, `company`, `location`, and `region`.

    Example input:
    [
        {"linkedin_url": "https://www.linkedin.com/in/janedoe/", "name": "Jane Doe"},
        {"linkedin_url": "https://www.linkedin.com/in/johndoe/"}
    ]

    Args:
        leads: List of prospect dicts with at least linkedin_url.
    """
    result = pipeline.add_prospects(leads)
    return (
        f"Imported {result['added']} new prospects "
        f"({result['duplicates']} duplicates skipped). "
        f"Pipeline total: {result['total']}."
    )


# ── Tool 6: Search Leads ────────────────────────────────────────


@mcp.tool()
def search_leads(
    keywords: str,
    location: str | None = None,
    geo_id: str | None = None,
    max_results: int = 20,
) -> str:
    """Search LinkedIn for prospects by keywords and location.

    Opens a browser, runs the search, and adds results to the pipeline.

    Args:
        keywords: Search terms (e.g. "Marketing Director SaaS", "VP Growth fintech").
        location: Location name (e.g. "London", "Singapore", "New York").
            Automatically resolved to LinkedIn geo ID.
        geo_id: LinkedIn geo ID (overrides location). Use for locations not in the built-in map.
        max_results: Approximate max number of results to return (default: 20).

    Supported locations (auto-resolved):
        Cities: New York, San Francisco, Los Angeles, Chicago, Boston, Seattle,
        Austin, Denver, Miami, London, Berlin, Paris, Amsterdam, Dublin, Toronto,
        Vancouver, Sydney, Melbourne, Mumbai, Bangalore, Delhi, Dubai, Abu Dhabi,
        Hong Kong, Tokyo, Tel Aviv, Sao Paulo, Singapore.
        Countries: US, UK, India, Canada, Australia, Germany, France, Netherlands,
        UAE, Singapore, Japan, Brazil, Israel.
    """
    from playwright.sync_api import sync_playwright

    def _do_search():
        with sync_playwright() as pw:
            context, page = launch_browser(pw)
            try:
                if not verify_login(page):
                    return "Not logged in. Call linkedin_login first."

                max_pages = max(1, max_results // 10)
                results = search.search_people(
                    page,
                    keywords=keywords,
                    location=location,
                    geo_id=geo_id,
                    max_pages=max_pages,
                )

                if not results:
                    loc_msg = f" in {location}" if location else ""
                    return f"No results found for '{keywords}'{loc_msg}."

                # Add to pipeline
                add_result = pipeline.add_prospects(results)

                # Format response
                lines = [
                    f"Found {len(results)} prospects for '{keywords}'"
                    + (f" in {location}" if location else "")
                    + f" ({add_result['added']} new, {add_result['duplicates']} already in pipeline):",
                    "",
                ]
                for i, r in enumerate(results[:30], 1):
                    lines.append(
                        f"  {i}. {r['name']} — {r['title'][:60]}"
                        + (f" ({r['location'][:30]})" if r.get('location') else "")
                    )

                lines.append(f"\nPipeline total: {add_result['total']}")
                return "\n".join(lines)
            finally:
                context.close()

    return _run_sync(_do_search)


# ── Tool 7: View Pipeline ───────────────────────────────────────


@mcp.tool()
def view_pipeline(
    status: str | None = None,
    region: str | None = None,
    limit: int = 50,
) -> str:
    """View the current outreach pipeline.

    Args:
        status: Filter by status (Discovered, Ready, Sent, Accepted, Follow-up Sent, Failed).
        region: Filter by region/location.
        limit: Max number of prospects to show (default: 50).
    """
    summary = pipeline.get_summary()
    prospects = pipeline.get_prospects(status=status, region=region, limit=limit)

    lines = ["=== Pipeline Summary ==="]
    lines.append(f"Total prospects: {summary['total']}")
    lines.append("")

    if summary["by_status"]:
        lines.append("By Status:")
        for s, count in sorted(summary["by_status"].items()):
            lines.append(f"  {s}: {count}")
        lines.append("")

    if summary["by_region"]:
        lines.append("By Region:")
        for r, count in sorted(summary["by_region"].items()):
            if r:
                lines.append(f"  {r}: {count}")
        lines.append("")

    filter_desc = []
    if status:
        filter_desc.append(f"status={status}")
    if region:
        filter_desc.append(f"region={region}")
    filter_str = f" ({', '.join(filter_desc)})" if filter_desc else ""

    if prospects:
        lines.append(f"Prospects{filter_str} (showing {len(prospects)}):")
        for i, p in enumerate(prospects, 1):
            note_indicator = " [has note]" if p.get("connection_note") else ""
            lines.append(
                f"  {i}. [{p.get('status', '?')}] {p.get('name', '?')} — "
                f"{p.get('title', '')[:50]}{note_indicator}"
            )
            if p.get("linkedin_url"):
                lines.append(f"     {p['linkedin_url']}")
    else:
        lines.append(f"No prospects found{filter_str}.")

    return "\n".join(lines)


# ── Tool 8: Get Prospects (structured) ───────────────────────────


@mcp.tool()
def get_prospects(
    status: str | None = None,
    region: str | None = None,
    limit: int = 20,
) -> str:
    """Get prospect data as JSON for processing.

    Use this to get prospect details for generating personalized notes.
    Returns structured data you can use to craft messages.

    Args:
        status: Filter by status (e.g. "Discovered" for prospects needing notes).
        region: Filter by region.
        limit: Max results (default: 20).
    """
    prospects = pipeline.get_prospects(status=status, region=region, limit=limit)
    return json.dumps(prospects, indent=2)


# ── Tool 9: Save Notes ──────────────────────────────────────────


@mcp.tool()
def save_notes(notes: list[dict]) -> str:
    """Save personalized connection notes for prospects.

    After generating notes (using prospect info + user profile),
    call this to save them. Prospects with notes are marked as "Ready"
    for sending.

    Args:
        notes: List of {"linkedin_url": "...", "connection_note": "..."} dicts.
            Each note must be ≤300 characters (LinkedIn limit).

    Example:
    [
        {
            "linkedin_url": "https://www.linkedin.com/in/janedoe/",
            "connection_note": "Hi Jane, I noticed we're both in the SaaS marketing space..."
        }
    ]
    """
    # Validate note lengths
    too_long = []
    for n in notes:
        note_text = n.get("connection_note", "")
        if len(note_text) > 300:
            too_long.append(
                f"  {n.get('linkedin_url', '?')}: {len(note_text)} chars"
            )

    if too_long:
        return (
            f"Error: {len(too_long)} notes exceed the 300-character LinkedIn limit:\n"
            + "\n".join(too_long)
            + "\n\nPlease shorten them and try again."
        )

    updated = pipeline.bulk_update_notes(notes)
    return f"Saved {updated} connection notes. These prospects are now Ready for outreach."


# ── Tool 10: Save Follow-up Messages ────────────────────────────


@mcp.tool()
def save_followup_messages(messages: list[dict]) -> str:
    """Save follow-up messages for accepted connections.

    Args:
        messages: List of {"linkedin_url": "...", "followup_message": "..."} dicts.
            Each message should be ≤500 characters.
    """
    prospects = pipeline.load()
    pid_to_msg = {}
    for m in messages:
        url = m.get("linkedin_url", "")
        if "/in/" in url:
            pid = url.rstrip("/").split("/in/")[-1].split("?")[0].lower()
            pid_to_msg[pid] = m.get("followup_message", "")

    updated = 0
    for p in prospects:
        url = p.get("linkedin_url", "")
        if "/in/" in url:
            pid = url.rstrip("/").split("/in/")[-1].split("?")[0].lower()
            if pid in pid_to_msg:
                p["followup_message"] = pid_to_msg[pid]
                updated += 1

    pipeline.save(prospects)
    return f"Saved {updated} follow-up messages."


# ── Tool 11: Send Connections ────────────────────────────────────


@mcp.tool()
def send_connections(limit: int = 5, dry_run: bool = True) -> str:
    """Send connection requests to prospects with saved notes.

    Only sends to prospects with status "Ready" (have a connection note).

    IMPORTANT: Set dry_run=true first to preview, then dry_run=false to send.

    Args:
        limit: Max number of connection requests to send (default: 5).
        dry_run: If true, preview only — don't actually send (default: true).
    """
    from playwright.sync_api import sync_playwright

    prospects = pipeline.get_prospects(status="Ready", limit=limit)
    if not prospects:
        return "No prospects ready to send. Add notes first with save_notes."

    cfg = config.load_config()
    daily_limit = cfg.get("daily_limits", {}).get("connection_requests", 20)

    if limit > daily_limit:
        return (
            f"Limit ({limit}) exceeds daily limit ({daily_limit}). "
            f"Reduce limit or update config."
        )

    if dry_run:
        lines = [f"[DRY RUN] Would send {len(prospects)} connection requests:", ""]
        for i, p in enumerate(prospects, 1):
            note = p.get("connection_note", "")[:80]
            lines.append(f"  {i}. {p['name']} ({p.get('company', '')}) — \"{note}...\"")
        lines.append(f"\nCall send_connections with dry_run=false to send for real.")
        return "\n".join(lines)

    def _do_send():
        with sync_playwright() as pw:
            context, page = launch_browser(pw)
            try:
                if not verify_login(page):
                    return "Not logged in. Call linkedin_login first."

                results = {"sent": 0, "failed": 0, "skipped": 0, "details": []}

                for i, prospect in enumerate(prospects):
                    name = prospect["name"]
                    url = prospect.get("linkedin_url")
                    note = prospect.get("connection_note", "")

                    if not url:
                        results["skipped"] += 1
                        results["details"].append(f"  SKIP: {name} — no URL")
                        continue

                    status = send_connection_request(page, url, note, name)

                    if status == "sent":
                        pipeline.mark_sent(url, success=True)
                        results["sent"] += 1
                        results["details"].append(f"  SENT: {name}")
                    elif status in ("already_connected", "already_pending"):
                        pipeline.update_prospect(url, status=status.replace("_", " ").title())
                        results["skipped"] += 1
                        results["details"].append(f"  SKIP: {name} — {status}")
                    else:
                        pipeline.mark_sent(url, success=False, error=status)
                        results["failed"] += 1
                        results["details"].append(f"  FAIL: {name} — {status}")

                    import time
                    delays = config.load_config().get("delays", {})
                    time.sleep(delays.get("between_prospects", 5))

                lines = [
                    "=== Outreach Results ===",
                    f"Sent: {results['sent']}",
                    f"Failed: {results['failed']}",
                    f"Skipped: {results['skipped']}",
                    "",
                ] + results["details"]

                return "\n".join(lines)
            finally:
                context.close()

    return _run_sync(_do_send)


# ── Tool 12: Check Acceptances ───────────────────────────────────


@mcp.tool()
def check_acceptances() -> str:
    """Check which sent connection requests have been accepted.

    Opens LinkedIn and compares your connections list against sent prospects.
    Updates the pipeline with acceptance status.
    """
    from playwright.sync_api import sync_playwright

    def _do_check():
        sent = pipeline.get_prospects(status="Sent")
        if not sent:
            return "No sent connections to check."

        # Build lookup
        sent_by_pid = {}
        for p in sent:
            url = p.get("linkedin_url", "")
            if url and "/in/" in url:
                pid = url.rstrip("/").split("/in/")[-1].lower()
                sent_by_pid[pid] = p

        with sync_playwright() as pw:
            context, page = launch_browser(pw)
            try:
                if not verify_login(page):
                    return "Not logged in. Call linkedin_login first."

                connections = check_acceptances_on_page(page)
            finally:
                context.close()

        accepted = []
        for conn in connections:
            pid = conn["publicId"].lower()
            if pid in sent_by_pid:
                prospect = sent_by_pid[pid]
                pipeline.mark_accepted(prospect["linkedin_url"])
                accepted.append(f"  {conn['name']} ({prospect.get('company', '')})")

        if accepted:
            lines = [f"Found {len(accepted)} new acceptances:", ""] + accepted
            lines.append(f"\n{len(sent_by_pid) - len(accepted)} still pending.")
            return "\n".join(lines)
        else:
            return f"No new acceptances found. {len(sent_by_pid)} still pending."

    return _run_sync(_do_check)


# ── Tool 13: Send Follow-ups ────────────────────────────────────


@mcp.tool()
def send_followups(limit: int = 5, dry_run: bool = True) -> str:
    """Send follow-up DMs to accepted connections.

    Only sends to accepted connections that have a followup_message saved
    and haven't been followed up yet.

    Args:
        limit: Max messages to send (default: 5).
        dry_run: Preview only if true (default: true).
    """
    from playwright.sync_api import sync_playwright

    all_prospects = pipeline.load()
    to_followup = [
        p for p in all_prospects
        if p.get("status") == "Accepted"
        and p.get("followup_message")
        and not p.get("followup_sent")
    ][:limit]

    if not to_followup:
        return (
            "No accepted connections ready for follow-up. "
            "Check acceptances first, then save follow-up messages."
        )

    if dry_run:
        lines = [f"[DRY RUN] Would send {len(to_followup)} follow-up messages:", ""]
        for i, p in enumerate(to_followup, 1):
            msg = p.get("followup_message", "")[:80]
            lines.append(f"  {i}. {p['name']} — \"{msg}...\"")
        lines.append(f"\nCall send_followups with dry_run=false to send.")
        return "\n".join(lines)

    def _do_followup():
        with sync_playwright() as pw:
            context, page = launch_browser(pw)
            try:
                if not verify_login(page):
                    return "Not logged in. Call linkedin_login first."

                sent = 0
                details = []

                for p in to_followup:
                    url = p.get("linkedin_url")
                    if not url:
                        continue

                    status = send_followup_message(
                        page, url, p["followup_message"], p["name"]
                    )

                    if status == "followup_sent":
                        pipeline.mark_followup_sent(url)
                        sent += 1
                        details.append(f"  SENT: {p['name']}")
                    else:
                        details.append(f"  FAIL: {p['name']} — {status}")

                    import time
                    time.sleep(config.load_config().get("delays", {}).get("between_prospects", 5))

                lines = [f"Follow-up results: {sent}/{len(to_followup)} sent", ""] + details
                return "\n".join(lines)
            finally:
                context.close()

    return _run_sync(_do_followup)


# ── Tool 14: Read Conversations ──────────────────────────────────


@mcp.tool()
def read_conversations(limit: int = 5) -> str:
    """Read message threads with accepted connections.

    Opens LinkedIn messaging and reads conversations with recently
    accepted connections.

    Args:
        limit: Max conversations to read (default: 5).
    """
    from playwright.sync_api import sync_playwright

    accepted = pipeline.get_prospects(status="Accepted", limit=limit)
    followedup = pipeline.get_prospects(status="Follow-up Sent", limit=limit)
    targets = (accepted + followedup)[:limit]

    if not targets:
        return "No accepted connections to read conversations from."

    def _do_read():
        with sync_playwright() as pw:
            context, page = launch_browser(pw)
            try:
                if not verify_login(page):
                    return "Not logged in. Call linkedin_login first."

                conversations = []
                for p in targets:
                    url = p.get("linkedin_url")
                    if not url:
                        continue

                    convo = read_conversation(page, url, p["name"])
                    conversations.append(convo)

                    import time
                    time.sleep(2)

                if not conversations:
                    return "No conversations found."

                lines = []
                for convo in conversations:
                    lines.append(f"--- {convo['name']} ---")
                    if convo.get("error"):
                        lines.append(f"  Error: {convo['error']}")
                    elif convo["messages"]:
                        for msg in convo["messages"][-5:]:  # Last 5 messages
                            lines.append(f"  [{msg['sender']}]: {msg['text'][:200]}")
                    else:
                        lines.append("  No messages found.")
                    lines.append("")

                return "\n".join(lines)
            finally:
                context.close()

    return _run_sync(_do_read)


# ── Tool 15: Export Pipeline ─────────────────────────────────────


@mcp.tool()
def export_pipeline(format: str = "csv") -> str:
    """Export the pipeline data.

    Args:
        format: Export format — "csv" for CSV string, "json" for raw JSON.
    """
    if format == "json":
        data = pipeline.load()
        return json.dumps(data, indent=2)
    elif format == "csv":
        return pipeline.export_csv()
    else:
        return f"Unknown format: {format}. Use 'csv' or 'json'."


# ── Tool 16: Generate Template Notes (fallback) ─────────────────


@mcp.tool()
def generate_template_notes(limit: int = 10) -> str:
    """Generate connection notes using templates (fallback method).

    This uses built-in templates as a quick way to generate notes.
    For better quality, use Claude to generate AI-personalized notes instead:
    1. Call get_prospects(status="Discovered") to get prospect data
    2. Generate a unique ≤300 char note for each using their profile info
    3. Call save_notes to save them

    Args:
        limit: Max number of notes to generate (default: 10).
    """
    profile = config.load_profile()
    if not profile:
        return "Set up your profile first with setup_profile."

    needing = pipeline.get_prospects_needing_notes(limit=limit)
    if not needing:
        return "All prospects already have notes, or no prospects in pipeline."

    notes = []
    for prospect in needing:
        note = personalize.generate_template_note(prospect, profile)
        notes.append({
            "linkedin_url": prospect["linkedin_url"],
            "connection_note": note,
        })

    updated = pipeline.bulk_update_notes(notes)

    lines = [f"Generated {updated} template-based notes:", ""]
    for n in notes:
        lines.append(f"  {n['linkedin_url']}")
        lines.append(f"    \"{n['connection_note'][:80]}...\"")

    lines.append(
        "\nTip: For better results, generate AI-personalized notes instead — "
        "call get_prospects and craft unique notes per profile."
    )
    return "\n".join(lines)


# ── Tool 17: Remove Prospect ────────────────────────────────────


@mcp.tool()
def remove_prospect(linkedin_url: str) -> str:
    """Remove a prospect from the pipeline.

    Args:
        linkedin_url: The LinkedIn profile URL to remove.
    """
    prospects = pipeline.load()
    pid = linkedin_url.rstrip("/").split("/in/")[-1].split("?")[0].lower()

    original_count = len(prospects)
    prospects = [
        p for p in prospects
        if not (
            p.get("linkedin_url", "").rstrip("/").split("/in/")[-1].split("?")[0].lower() == pid
        )
    ]

    if len(prospects) == original_count:
        return f"Prospect not found: {linkedin_url}"

    pipeline.save(prospects)
    return f"Removed prospect. Pipeline: {len(prospects)} remaining."


# ── Entry point ──────────────────────────────────────────────────


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
