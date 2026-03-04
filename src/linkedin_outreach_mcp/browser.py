"""Playwright-based LinkedIn browser automation.

Handles the real browser interactions:
- Login session management
- Profile navigation
- Connection request sending
- Acceptance checking
- Follow-up messaging
- Conversation reading

Uses a persistent browser context at ~/.linkedin-outreach-mcp/browser/
to maintain the LinkedIn session across runs.
"""

import logging
import time

from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

from . import config

log = logging.getLogger(__name__)

# Human-like pacing delays (seconds)
DELAY_ACTION = 2
DELAY_PROSPECT = 5
DELAY_PAGE = 3


def _get_delays() -> dict:
    """Get configured delays, falling back to defaults."""
    cfg = config.load_config()
    delays = cfg.get("delays", {})
    return {
        "action": delays.get("between_actions", DELAY_ACTION),
        "prospect": delays.get("between_prospects", DELAY_PROSPECT),
        "page": delays.get("page_load", DELAY_PAGE),
    }


def launch_browser(playwright):
    """Launch browser with persistent LinkedIn session.

    Returns (context, page) tuple.
    """
    user_data_dir = config.BROWSER_DIR
    config.ensure_data_dir()

    context = playwright.chromium.launch_persistent_context(
        user_data_dir,
        headless=False,
        viewport={"width": 1280, "height": 900},
        args=["--disable-blink-features=AutomationControlled"],
    )
    page = context.pages[0] if context.pages else context.new_page()
    return context, page


def verify_login(page) -> bool:
    """Check that cookies are valid by visiting LinkedIn feed."""
    delays = _get_delays()
    page.goto(
        "https://www.linkedin.com/feed/",
        wait_until="domcontentloaded",
        timeout=30000,
    )
    time.sleep(delays["page"])

    url = page.url
    if "/login" in url or "/authwall" in url or "/checkpoint" in url:
        return False
    return True


def do_login(page) -> bool:
    """Navigate to LinkedIn login page and wait for user to log in.

    Returns True if login succeeded within 120 seconds.
    """
    page.goto(
        "https://www.linkedin.com/login",
        wait_until="domcontentloaded",
        timeout=30000,
    )

    # Poll for up to 120 seconds for the user to log in
    for _ in range(60):
        time.sleep(2)
        url = page.url
        if "/feed" in url or "/mynetwork" in url:
            return True
        if "/login" not in url and "/authwall" not in url and "/checkpoint" not in url:
            return True

    return False


# ── Element helpers ──────────────────────────────────────────────


def _js_click(element):
    """Click via JavaScript to bypass sticky nav / overlay interception."""
    element.evaluate("el => el.click()")


def _scroll_to(page, element):
    """Scroll element into view, centered."""
    element.evaluate('el => el.scrollIntoView({block: "center"})')
    time.sleep(0.5)


def _find_by_text(page, tag, targets, exact=True):
    """Find an element by tag whose visible text matches one of the targets."""
    for el in page.query_selector_all(tag):
        if not el.is_visible():
            continue
        text = (el.inner_text() or "").strip().lower()
        if exact:
            if text in targets:
                return el
        else:
            if any(t in text for t in targets):
                return el
    return None


def _find_button_by_aria(page, keyword):
    """Find a visible button whose aria-label contains the keyword."""
    for btn in page.query_selector_all("button"):
        if not btn.is_visible():
            continue
        aria = (btn.get_attribute("aria-label") or "").lower()
        if keyword in aria:
            return btn
    return None


# ── Connection request sending ───────────────────────────────────


def send_connection_request(page, profile_url: str, note: str, name: str) -> str:
    """Navigate to a profile and send a connection request with note.

    Handles LinkedIn's UI variations:
    - "Connect" as <a> link in header
    - "Connect" as <button>
    - "Connect" hidden in "More" dropdown

    Returns status string: "sent", "already_connected", "already_pending",
    "no_connect_button", "sent_without_note", or error description.
    """
    delays = _get_delays()
    page.goto(profile_url, wait_until="domcontentloaded")
    time.sleep(delays["page"])

    try:
        connect_clicked = False

        # Strategy 1: "Connect" <a> link
        link = _find_by_text(page, "a", {"connect"})
        if link:
            _scroll_to(page, link)
            _js_click(link)
            connect_clicked = True

        # Strategy 2: "Connect" <button>
        if not connect_clicked:
            btn = _find_by_text(page, "button", {"connect"})
            if not btn:
                btn = _find_button_by_aria(page, "invite")
            if btn:
                _scroll_to(page, btn)
                _js_click(btn)
                connect_clicked = True

        # Strategy 3: "More" dropdown → "Connect"
        if not connect_clicked:
            more_btn = None

            # Find Follow button as anchor, then walk up DOM for three-dots
            follow_btn = None
            for b in page.query_selector_all("button"):
                if not b.is_visible():
                    continue
                aria = (b.get_attribute("aria-label") or "").lower()
                if aria.startswith("follow "):
                    follow_btn = b
                    break

            if follow_btn:
                dots_handle = follow_btn.evaluate_handle("""(followBtn) => {
                    let parent = followBtn.parentElement;
                    for (let i = 0; i < 5; i++) {
                        if (!parent) break;
                        const btns = parent.querySelectorAll('button');
                        for (const btn of btns) {
                            const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
                            if (aria.includes('more') && btn !== followBtn && btn.offsetParent !== null) {
                                return btn;
                            }
                        }
                        parent = parent.parentElement;
                    }
                    return null;
                }""")
                tag = dots_handle.evaluate("el => el ? el.tagName : null")
                if tag:
                    more_btn = dots_handle
            else:
                more_btn = _find_button_by_aria(page, "more actions")

            if more_btn:
                more_btn.evaluate('el => el.scrollIntoView({block: "center"})')
                time.sleep(0.5)
                more_btn.evaluate("el => el.click()")
                time.sleep(1.5)

                for selector in ['[role="menuitem"]', '.artdeco-dropdown__item']:
                    for item in page.query_selector_all(selector):
                        if not item.is_visible():
                            continue
                        text = (item.inner_text() or "").strip().lower()
                        if "connect" in text:
                            _js_click(item)
                            connect_clicked = True
                            break
                    if connect_clicked:
                        break

                if not connect_clicked:
                    for span in page.query_selector_all("span"):
                        if not span.is_visible():
                            continue
                        text = (span.inner_text() or "").strip().lower()
                        if text == "connect":
                            span.evaluate("el => el.click()")
                            connect_clicked = True
                            break

        if not connect_clicked:
            msg_btn = _find_by_text(page, "button", {"message"})
            if msg_btn:
                return "already_connected"
            pending_btn = _find_by_text(page, "button", {"pending"})
            if pending_btn:
                return "already_pending"
            return "no_connect_button"

        time.sleep(delays["action"])

        # Handle the connection modal
        add_note_btn = _find_by_text(page, "button", {"add a note"}, exact=False)

        if add_note_btn:
            _js_click(add_note_btn)
            time.sleep(1)

            textarea = page.query_selector(
                'textarea[name="message"], textarea#custom-message, textarea'
            )
            if textarea:
                textarea.fill(note[:300])  # LinkedIn 300 char limit
                time.sleep(1)

                send_btn = page.query_selector(
                    'button[aria-label="Send invitation"]'
                )
                if not send_btn:
                    send_btn = page.query_selector(
                        'button[aria-label="Send now"]'
                    )
                if send_btn:
                    _js_click(send_btn)
                    time.sleep(delays["action"])
                    return "sent"
                else:
                    return "send_button_not_found"
            else:
                return "textarea_not_found"
        else:
            send_btn = _find_by_text(
                page, "button", {"send", "send now", "send without a note"}
            )
            if send_btn:
                _js_click(send_btn)
                time.sleep(delays["action"])
                return "sent_without_note"
            return "modal_not_found"

    except PwTimeout:
        return "timeout"
    except Exception as e:
        return f"error: {str(e)}"


# ── Acceptance checking ──────────────────────────────────────────


def check_acceptances_on_page(page) -> list[dict]:
    """Scrape the connections page and return list of {name, publicId}."""
    delays = _get_delays()
    page.goto(
        "https://www.linkedin.com/mynetwork/invite-connect/connections/",
        wait_until="domcontentloaded",
    )
    time.sleep(5)

    # Scroll to load connections
    for _ in range(5):
        page.evaluate("window.scrollBy(0, 600)")
        time.sleep(1)

    connections = page.evaluate("""() => {
        const main = document.querySelector('main') || document.body;
        const results = [];
        const seen = new Set();
        const links = main.querySelectorAll('a[href*="/in/"]');
        for (const link of links) {
            const href = link.getAttribute('href') || '';
            if (!href.includes('/in/')) continue;
            const publicId = href.split('/in/')[1]?.split('?')[0]?.replace(/\\/$/,'');
            if (!publicId || seen.has(publicId)) continue;
            let name = link.innerText.trim().split('\\n')[0].trim();
            if (name.length < 2 || name.length > 100) continue;
            seen.add(publicId);
            results.push({ name, publicId });
        }
        return results;
    }""")

    return connections


# ── Follow-up messaging ──────────────────────────────────────────


def send_followup_message(page, profile_url: str, message: str, name: str) -> str:
    """Send a DM to an already-connected person.

    Returns: "followup_sent", "no_message_button", "compose_not_found",
    "timeout", or error string.
    """
    delays = _get_delays()
    page.goto(profile_url, wait_until="domcontentloaded")
    time.sleep(delays["page"])

    try:
        msg_btn = _find_by_text(page, "button", {"message"})
        if not msg_btn:
            return "no_message_button"

        _scroll_to(page, msg_btn)
        _js_click(msg_btn)
        time.sleep(delays["action"])

        # Find compose area
        compose = None
        for sel in [
            'div.msg-form__contenteditable[contenteditable="true"]',
            'div[role="textbox"][contenteditable="true"]',
            'div.msg-form__msg-content-container div[contenteditable="true"]',
        ]:
            compose = page.query_selector(sel)
            if compose:
                break

        if not compose:
            return "compose_not_found"

        compose.click()
        time.sleep(0.5)
        page.keyboard.type(message, delay=20)
        time.sleep(1)

        # Find Send button
        send_btn = None
        for btn in page.query_selector_all(
            'button[type="submit"], button.msg-form__send-button'
        ):
            if btn.is_visible():
                text = (btn.inner_text() or "").strip().lower()
                aria = (btn.get_attribute("aria-label") or "").lower()
                if "send" in text or "send" in aria:
                    send_btn = btn
                    break

        if not send_btn:
            for btn in page.query_selector_all(
                'form.msg-form button, div.msg-form button'
            ):
                if btn.is_visible():
                    text = (btn.inner_text() or "").strip().lower()
                    if text == "send":
                        send_btn = btn
                        break

        if not send_btn:
            page.keyboard.press("Enter")
            time.sleep(delays["action"])
            return "followup_sent"

        _js_click(send_btn)
        time.sleep(delays["action"])
        return "followup_sent"

    except PwTimeout:
        return "timeout"
    except Exception as e:
        return f"error: {str(e)}"


# ── Conversation reading ─────────────────────────────────────────


def read_conversation(page, profile_url: str, name: str) -> dict:
    """Open a conversation with someone and read the messages.

    Returns: {"name": str, "messages": [{"sender": str, "text": str}]}
    """
    delays = _get_delays()
    page.goto(profile_url, wait_until="domcontentloaded")
    time.sleep(delays["page"])

    msg_btn = _find_by_text(page, "button", {"message"})
    if not msg_btn:
        return {"name": name, "messages": [], "error": "not_connected"}

    _scroll_to(page, msg_btn)
    _js_click(msg_btn)
    time.sleep(delays["action"])

    # Read messages from the conversation overlay
    messages = page.evaluate("""() => {
        const msgs = [];
        const bubbles = document.querySelectorAll(
            '.msg-s-message-list__event, .msg-s-event-listitem'
        );
        for (const bubble of bubbles) {
            const senderEl = bubble.querySelector(
                '.msg-s-message-group__name, .msg-s-message-group__profile-link'
            );
            const textEl = bubble.querySelector(
                '.msg-s-event-listitem__body, .msg-s-message-group__message-body'
            );
            if (textEl) {
                msgs.push({
                    sender: senderEl ? senderEl.innerText.trim() : 'Unknown',
                    text: textEl.innerText.trim()
                });
            }
        }
        return msgs;
    }""")

    return {"name": name, "messages": messages}
