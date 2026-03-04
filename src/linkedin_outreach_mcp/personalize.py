"""Fallback template-based message personalization.

These templates are used as fallbacks when Claude's AI-generated notes
are not available. The primary personalization approach is for Claude to
generate notes directly using the prospect's profile info and the user's
profile context.

Connection requests: 300 character limit.
Direct messages: 500 character limit.
"""

import re


CONNECTION_TEMPLATES = {
    "admire_work": (
        "Hi {first_name}, I came across your work at {company} and was"
        " impressed. I'm in {my_field} and keen to connect with"
        " professionals in {location}. Would love to be in your network!"
    ),
    "shared_industry": (
        "Hi {first_name}, I noticed we're both in the {industry} space."
        " I'm a {my_role} exploring opportunities in {location}."
        " Would love to connect!"
    ),
    "shared_role": (
        "Hi {first_name}, as a fellow {industry} professional,"
        " I'd love to connect. Always great to exchange ideas"
        " with leaders in {location}."
    ),
    "general": (
        "Hi {first_name}, I'm a {my_role} looking to connect"
        " with {industry} professionals in {location}."
        " Would love to be part of your network!"
    ),
}


FOLLOWUP_TEMPLATES = {
    "general": (
        "Hi {first_name},\n\n"
        "Thanks for connecting! I'm a {my_role} and really respect"
        " the work you're doing at {company}.\n\n"
        "I'd love to hear about your experience in {location}."
        " Would you be open to a brief chat?\n\n"
        "Best,\n{my_name}"
    ),
}


def generate_template_note(
    prospect: dict,
    profile: dict,
    template_key: str = "general",
) -> str:
    """Generate a connection note from templates.

    This is the fallback when AI-generated notes are not available.

    Args:
        prospect: Prospect dict with name, title, company, location, etc.
        profile: User profile dict with name, headline, etc.
        template_key: Which template to use.

    Returns: Connection note string (≤300 chars).
    """
    template = CONNECTION_TEMPLATES.get(template_key, CONNECTION_TEMPLATES["general"])

    first_name = prospect.get("name", "").split()[0] if prospect.get("name") else ""
    company = prospect.get("company", "your company")
    location = prospect.get("location", "your region")
    title = prospect.get("title", "")

    # Infer industry from title
    industry = _infer_industry(title)

    my_name = profile.get("name", "")
    my_role = profile.get("headline", profile.get("current_role", {}).get("title", ""))
    my_field = profile.get("headline", "")

    # Fill template
    placeholders = re.findall(r"\{(\w+)\}", template)
    values = {
        "first_name": first_name,
        "company": company,
        "location": location,
        "industry": industry,
        "my_name": my_name,
        "my_role": my_role,
        "my_field": my_field,
    }
    for key in placeholders:
        if key not in values:
            values[key] = ""

    note = template.format(**values)

    if len(note) > 300:
        note = note[:297] + "..."
    return note


def generate_template_followup(prospect: dict, profile: dict) -> str:
    """Generate a follow-up message from templates.

    Returns: Follow-up message string (≤500 chars).
    """
    template = FOLLOWUP_TEMPLATES["general"]

    first_name = prospect.get("name", "").split()[0] if prospect.get("name") else ""
    company = prospect.get("company", "your company")
    location = prospect.get("location", "your region")

    my_name = profile.get("name", "")
    my_role = profile.get("headline", "")

    note = template.format(
        first_name=first_name,
        company=company,
        location=location,
        my_name=my_name,
        my_role=my_role,
    )

    if len(note) > 500:
        note = note[:497] + "..."
    return note


def _infer_industry(title: str) -> str:
    """Try to infer industry from a person's title."""
    title_lower = title.lower()
    industry_keywords = {
        "saas": "SaaS",
        "fintech": "fintech",
        "e-commerce": "e-commerce",
        "ecommerce": "e-commerce",
        "healthcare": "healthcare",
        "edtech": "edtech",
        "real estate": "real estate",
        "ai": "AI",
        "crypto": "crypto",
        "blockchain": "blockchain",
        "marketing": "marketing",
        "technology": "technology",
        "startup": "startups",
    }
    for keyword, industry in industry_keywords.items():
        if keyword in title_lower:
            return industry
    return "technology"
