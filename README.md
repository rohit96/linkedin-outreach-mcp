# LinkedIn Outreach MCP

An MCP (Model Context Protocol) server that automates LinkedIn outreach from [Claude Code](https://claude.com/claude-code). Discover prospects, send personalized connection requests, track acceptances, and manage follow-ups — all through natural conversation.

## What It Does

Tell Claude what you want:
- *"Find 20 marketing directors in London and send them personalized connection requests"*
- *"Import these LinkedIn URLs and generate connection notes for each person"*
- *"Check which of my sent connections got accepted and draft follow-up messages"*

The MCP server handles the browser automation while Claude handles the conversation and personalization.

### Pipeline Flow

```
Discover / Import → Personalize Notes → Send Connections → Track Acceptances → Follow Up
```

## Quick Start

### 1. Install

```bash
git clone https://github.com/rohitg00/linkedin-outreach-mcp.git
cd linkedin-outreach-mcp
pip install .
```

Install Playwright's browser:

```bash
playwright install chromium
```

### 2. Add to Claude Code

```bash
claude mcp add linkedin-outreach -- python -m linkedin_outreach_mcp
```

### 3. Use It

Open Claude Code and start a conversation:

```
You: Help me reach out to startup CTOs in Singapore

Claude: I'll help you with LinkedIn outreach to startup CTOs in Singapore.
       Let me first check if you're set up...
       [calls linkedin_login, setup_profile, search_leads, etc.]
```

## Available Tools

| Tool | Description |
|------|-------------|
| `linkedin_login` | Open browser for LinkedIn login (session persists) |
| `setup_profile` | Save your professional profile for personalization |
| `get_profile` | View your saved profile |
| `update_config` | Change daily limits and delay settings |
| `import_leads` | Import prospects from LinkedIn URLs |
| `search_leads` | Search LinkedIn by keywords + location |
| `view_pipeline` | View pipeline status and counts |
| `get_prospects` | Get prospect data as JSON (for note generation) |
| `save_notes` | Save personalized connection notes (≤300 chars) |
| `save_followup_messages` | Save follow-up DMs for accepted connections |
| `send_connections` | Send connection requests (supports dry run) |
| `check_acceptances` | Check which connections were accepted |
| `send_followups` | Send follow-up messages (supports dry run) |
| `read_conversations` | Read message threads with connections |
| `export_pipeline` | Export pipeline to CSV or JSON |
| `generate_template_notes` | Quick template-based notes (fallback) |
| `remove_prospect` | Remove a prospect from the pipeline |

## How It Works

### Input Modes

**Option A: Import a list**
Provide LinkedIn URLs directly:
```
You: Import these leads:
- https://www.linkedin.com/in/janedoe/
- https://www.linkedin.com/in/johnsmith/
```

**Option B: Search by criteria**
Describe your target audience:
```
You: Find 30 VP Marketing profiles in Dubai who work in SaaS
```

Claude will ask clarifying questions (titles, locations, number of leads) and search LinkedIn.

### Personalization

Claude reads each prospect's title, company, and location, then crafts a unique ≤300 character connection note. This is far more effective than generic templates.

Example:
> "Hi Sarah, your growth work at FinTechPro caught my eye — scaling in London's fintech scene is no small feat. I'm in product/growth and would love to connect!"

### Safety Features

- **Dry run by default** — preview what will be sent before sending
- **Daily limits** — 20 connections/day, 30 messages/day (configurable)
- **Human-like pacing** — 2-5 second delays between actions
- **Anti-detection** — real browser with persistent session, no automation headers
- **Confirmation required** — Claude always asks before sending real requests

## Supported Locations

The search tool auto-resolves these locations to LinkedIn geo IDs:

**Cities:** New York, San Francisco, Los Angeles, Chicago, Boston, Seattle, Austin, Denver, Miami, London, Berlin, Paris, Amsterdam, Dublin, Toronto, Vancouver, Sydney, Melbourne, Mumbai, Bangalore, Delhi, Hyderabad, Pune, Dubai, Abu Dhabi, Hong Kong, Tokyo, Tel Aviv, Sao Paulo, Singapore

**Countries:** US, UK, India, Canada, Australia, Germany, France, Netherlands, UAE, Singapore, Japan, Brazil, Israel

For other locations, pass a `geo_id` directly (find it in LinkedIn's URL when searching).

## Configuration

All data is stored in `~/.linkedin-outreach-mcp/`:

```
~/.linkedin-outreach-mcp/
├── profile.yaml      # Your professional profile
├── config.yaml       # Outreach settings
├── pipeline.json     # Prospect pipeline
└── browser/          # Persistent browser session
```

### Default Limits

| Setting | Default | Description |
|---------|---------|-------------|
| Daily connections | 20 | Max connection requests per day |
| Daily messages | 30 | Max DMs per day |
| Action delay | 2s | Between UI actions |
| Prospect delay | 5s | Between processing prospects |

Update via Claude: *"Set my daily connection limit to 15"*

## Example Workflows

### Cold Outreach Campaign

```
You: I want to reach out to 50 Head of Growth profiles in the Bay Area.
     I'm a product manager at TechCorp looking to network.

Claude: Let me set up your profile and search for prospects...
        [Sets up profile, searches LinkedIn, shows results]

Claude: I found 47 prospects. Let me generate personalized notes for each...
        [Generates unique 300-char notes using each prospect's info]

Claude: Here are the first 5 notes for review:
        1. "Hi Alex, your work scaling growth at Stripe is impressive..."
        2. "Hi Maria, fellow Bay Area tech professional here..."
        [...]

        Ready to send? I'll do a dry run first.

You: Looks good, send the first 10

Claude: [Sends 10 connection requests with personalized notes]
        Results: 10 sent, 0 failed
```

### Import and Personalize

```
You: Import these LinkedIn profiles and write connection notes:
     https://www.linkedin.com/in/person1/
     https://www.linkedin.com/in/person2/
     https://www.linkedin.com/in/person3/

Claude: [Imports 3 leads, generates AI-personalized notes, saves them]
        Ready to send when you are.
```

### Daily Check-in

```
You: Check my outreach status

Claude: [Checks acceptances, reads new conversations]

        Pipeline: 50 total
        - Sent: 35
        - Accepted: 12 (new: 3!)
        - Follow-up Sent: 5

        New acceptances:
        1. Jane Doe (CloudCo) — accepted yesterday
        2. John Smith (StartupXYZ) — accepted today

        Want me to draft follow-up messages?
```

## Development

```bash
# Clone
git clone https://github.com/rohitg00/linkedin-outreach-mcp.git
cd linkedin-outreach-mcp

# Install in development mode
pip install -e .
playwright install chromium

# Run the server directly (for testing)
python -m linkedin_outreach_mcp
```

### Project Structure

```
src/linkedin_outreach_mcp/
├── server.py        # MCP server — all tool definitions
├── browser.py       # Playwright browser automation
├── search.py        # LinkedIn people search
├── pipeline.py      # Prospect data management
├── config.py        # Configuration & profile
└── personalize.py   # Template-based fallback notes
```

## Disclaimer

This tool automates browser interactions with LinkedIn. Use responsibly:
- Respect LinkedIn's terms of service and rate limits
- Keep daily limits reasonable (the defaults are conservative)
- Don't spam — personalized, relevant outreach only
- You are responsible for your own LinkedIn account

## License

MIT
