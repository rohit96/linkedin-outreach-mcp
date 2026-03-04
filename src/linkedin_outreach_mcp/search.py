"""LinkedIn people search via browser automation.

Searches LinkedIn for prospects by title, location, and keywords,
then parses the search results page to extract profile information.
"""

import re
import time

# LinkedIn geo IDs for common locations.
# Users can also pass custom geo_ids directly.
GEO_IDS = {
    # Countries
    "united states": "103644278",
    "united kingdom": "101165590",
    "india": "102713980",
    "canada": "101174742",
    "australia": "101452733",
    "germany": "101282230",
    "france": "105015875",
    "netherlands": "102890719",
    "uae": "104305776",
    "singapore": "102454443",
    "japan": "106692834",
    "brazil": "106057199",
    "israel": "101620260",
    # Cities / Metros
    "new york": "105080838",
    "san francisco": "90000084",
    "san francisco bay area": "90000084",
    "los angeles": "102448103",
    "chicago": "103112676",
    "boston": "100506914",
    "seattle": "104116203",
    "austin": "104472866",
    "denver": "105763813",
    "miami": "100131069",
    "london": "102257491",
    "berlin": "106967730",
    "paris": "105015875",
    "amsterdam": "102890719",
    "dublin": "104738515",
    "toronto": "100025096",
    "vancouver": "103366113",
    "sydney": "104769905",
    "melbourne": "100727096",
    "mumbai": "103961728",
    "bangalore": "105214831",
    "delhi": "116726834",
    "hyderabad": "105556991",
    "pune": "114806696",
    "dubai": "104305776",
    "abu dhabi": "106818097",
    "hong kong": "103291313",
    "tokyo": "106692834",
    "tel aviv": "100994331",
    "sao paulo": "106383970",
}


def resolve_geo_id(location: str) -> str | None:
    """Resolve a location name to a LinkedIn geo ID.

    Returns the geo_id string, or None if not found.
    """
    key = location.strip().lower()
    return GEO_IDS.get(key)


def build_search_url(keywords: str, geo_id: str | None = None) -> str:
    """Build a LinkedIn people search URL."""
    encoded = keywords.replace(" ", "%20")
    url = (
        f"https://www.linkedin.com/search/results/people/"
        f"?keywords={encoded}&origin=FACETED_SEARCH"
    )
    if geo_id:
        url += f"&geoUrn=%5B%22{geo_id}%22%5D"
    return url


def parse_search_results(page) -> list[dict]:
    """Extract people from LinkedIn search results page.

    Returns list of:
    {"name": str, "publicId": str, "title": str, "location": str, "url": str}
    """
    return page.evaluate("""() => {
        const results = [];
        const main = document.querySelector('main') || document.body;

        // Strategy 1: Structured search result containers
        const containers = main.querySelectorAll(
            'li.reusable-search__result-container, ' +
            'li[class*="search-result"], ' +
            'div[data-view-name*="search-entity"]'
        );

        for (const container of containers) {
            const link = container.querySelector('a[href*="/in/"]');
            if (!link) continue;

            const href = link.getAttribute('href') || '';
            const publicId = href.split('/in/')[1]?.split('?')[0]?.replace(/\\/$/,'');
            if (!publicId) continue;

            const fullText = container.innerText || '';
            const lines = fullText.split('\\n').map(l => l.trim()).filter(l => l.length > 0);

            let name = '', title = '', location = '';

            for (let i = 0; i < lines.length; i++) {
                const line = lines[i];
                if (line.length < 3) continue;
                if (/^(1st|2nd|3rd|\\d+th|View|Connect|Follow|Message|Send|Pending)/.test(line)) continue;
                if (line.includes('mutual connection')) continue;
                if (line === '...' || line.startsWith('Current:') || line.startsWith('Past:')) continue;

                if (!name) {
                    name = line.replace(/[\\u{1F300}-\\u{1F9FF}\\u{2600}-\\u{26FF}\\u{2700}-\\u{27BF}]/gu, '').trim();
                    continue;
                }
                if (!title && line.length > 5) { title = line; continue; }
                if (!location && line.length > 3) { location = line; break; }
            }

            if (name && name.length > 2 && name.length < 80) {
                results.push({
                    name, publicId, title, location,
                    url: 'https://www.linkedin.com/in/' + publicId + '/'
                });
            }
        }

        // Strategy 2: Fallback — parse from all /in/ links on page
        if (results.length === 0) {
            const links = main.querySelectorAll('a[href*="/in/"]');
            const seen = new Set();

            for (const link of links) {
                const href = link.getAttribute('href') || '';
                const publicId = href.split('/in/')[1]?.split('?')[0]?.replace(/\\/$/,'');
                if (!publicId || seen.has(publicId)) continue;
                seen.add(publicId);

                let name = link.innerText.trim().split('\\n')[0].trim();
                name = name.replace(/[\\u{1F300}-\\u{1F9FF}\\u{2600}-\\u{26FF}\\u{2700}-\\u{27BF}]/gu, '').trim();
                if (name.length < 3 || name.length > 80) continue;
                if (/^(View|Connect|Follow|Message)/.test(name)) continue;

                const text = main.innerText;
                const nameIdx = text.indexOf(name);
                let title = '', location = '';
                if (nameIdx > -1) {
                    const snippet = text.substring(nameIdx, nameIdx + 500);
                    const slines = snippet.split('\\n').map(l => l.trim()).filter(l => l.length > 5);
                    if (slines.length > 1) title = slines[1];
                    if (slines.length > 2) location = slines[2];
                }

                results.push({
                    name, publicId, title, location,
                    url: 'https://www.linkedin.com/in/' + publicId + '/'
                });
            }
        }

        return results;
    }""")


def search_people(
    page,
    keywords: str,
    location: str | None = None,
    geo_id: str | None = None,
    max_pages: int = 2,
) -> list[dict]:
    """Search LinkedIn for people matching criteria.

    Args:
        page: Playwright page instance.
        keywords: Search terms (e.g. "Marketing Director SaaS").
        location: Human-readable location (e.g. "London"). Used to resolve geo_id.
        geo_id: LinkedIn geo ID. Overrides location if both provided.
        max_pages: Maximum number of result pages to scrape (default 2).

    Returns list of prospect dicts.
    """
    # Resolve geo_id from location name if not provided directly
    if not geo_id and location:
        geo_id = resolve_geo_id(location)

    url = build_search_url(keywords, geo_id)
    all_results = []
    seen_pids = set()

    for page_num in range(1, max_pages + 1):
        page_url = url if page_num == 1 else f"{url}&page={page_num}"

        page.goto(page_url, wait_until="domcontentloaded")
        time.sleep(4)

        # Scroll to load results
        for _ in range(4):
            page.evaluate("window.scrollBy(0, 800)")
            time.sleep(1.5)

        results = parse_search_results(page)

        for person in results:
            pid = person["publicId"].lower()
            if pid in seen_pids:
                continue
            seen_pids.add(pid)

            # Clean name artifacts
            name = person["name"]
            name = re.sub(r"\s*[•·]\s*(1st|2nd|3rd|\d+th)\s*$", "", name).strip()
            name = re.sub(r"\s*Premium\s*$", "", name).strip()
            if not name or len(name) < 3:
                continue

            # Extract company from title
            title = person.get("title", "")
            company = ""
            if " at " in title:
                company = title.split(" at ")[-1].strip()
            elif " @ " in title:
                company = title.split(" @ ")[-1].strip()

            all_results.append({
                "name": name,
                "title": title[:200],
                "company": company[:100],
                "location": person.get("location", "")[:100],
                "linkedin_url": person["url"],
                "region": (location or "").lower(),
                "source": "search",
            })

        if len(results) < 5:
            break  # No more results
        time.sleep(2)

    return all_results
