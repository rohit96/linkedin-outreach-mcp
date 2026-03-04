"""Configuration and profile management.

Stores user data in ~/.linkedin-outreach-mcp/:
  - profile.yaml   — user's name, role, company, value prop (for personalization)
  - config.yaml    — outreach settings (daily limits, etc.)
  - browser/       — Playwright persistent browser context (LinkedIn session)
  - pipeline.json  — prospect pipeline data
"""

import os
import yaml

DATA_DIR = os.path.expanduser("~/.linkedin-outreach-mcp")
PROFILE_PATH = os.path.join(DATA_DIR, "profile.yaml")
CONFIG_PATH = os.path.join(DATA_DIR, "config.yaml")
PIPELINE_PATH = os.path.join(DATA_DIR, "pipeline.json")
BROWSER_DIR = os.path.join(DATA_DIR, "browser")

DEFAULT_CONFIG = {
    "daily_limits": {
        "connection_requests": 20,
        "messages": 30,
    },
    "delays": {
        "between_actions": 2,
        "between_prospects": 5,
        "page_load": 3,
    },
}


def ensure_data_dir():
    """Create the data directory if it doesn't exist."""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(BROWSER_DIR, exist_ok=True)


def load_profile() -> dict:
    """Load user profile from disk. Returns empty dict if not set up."""
    if not os.path.exists(PROFILE_PATH):
        return {}
    with open(PROFILE_PATH, "r") as f:
        return yaml.safe_load(f) or {}


def save_profile(profile: dict):
    """Save user profile to disk."""
    ensure_data_dir()
    with open(PROFILE_PATH, "w") as f:
        yaml.dump(profile, f, default_flow_style=False, allow_unicode=True)


def load_config() -> dict:
    """Load outreach config from disk. Returns defaults if not set up."""
    if not os.path.exists(CONFIG_PATH):
        return dict(DEFAULT_CONFIG)
    with open(CONFIG_PATH, "r") as f:
        data = yaml.safe_load(f) or {}
    # Merge with defaults so new keys are always present
    merged = dict(DEFAULT_CONFIG)
    merged.update(data)
    return merged


def save_config(config: dict):
    """Save outreach config to disk."""
    ensure_data_dir()
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


def is_setup_complete() -> bool:
    """Check if the user has completed initial setup (profile exists)."""
    profile = load_profile()
    return bool(profile.get("name"))


def is_logged_in() -> bool:
    """Check if a browser session directory exists (may still be expired)."""
    return os.path.isdir(BROWSER_DIR) and len(os.listdir(BROWSER_DIR)) > 0
