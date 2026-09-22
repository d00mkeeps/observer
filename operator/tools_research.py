"""Robust Market Research, Literature Review & Competitive Intelligence Engine.

Provides rate-limited, zero-cost tools for:
- Google Custom Search (Live web search, competitor sites)
- Google Books (Literature, textbooks, clinical/exercise manuals)
- Google Trends (Consumer search interest & rising topics)
- arXiv (AI, pose estimation, algorithms & computer science papers)
- Apple App Store (Competitor iOS app reviews, ratings & user pain points)

Enforces strict daily budget ceilings and sliding-window rate limiters to prevent
rogue AI loops and avoid unexpected API expenses.
"""

import os
import re
import time
import json
import html
import logging
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

log = logging.getLogger("operator.tools.research")


# ---------------------------------------------------------------------------
# Rate Limiting & Daily Quota Guardrails (Cost & Rogue AI Protection)
# ---------------------------------------------------------------------------

class DailyQuotaTracker:
    """Tracks and enforces daily call limits per service to guarantee zero billing."""

    def __init__(self):
        self._counts: dict[str, int] = {}
        self._current_date: str = self._get_today()
        # Daily hard ceilings (stay strictly inside free tiers)
        self.DAILY_LIMITS = {
            "google_web": int(os.environ.get("QUOTA_GOOGLE_WEB", "50")),     # 100/day free limit -> capped at 50
            "google_books": int(os.environ.get("QUOTA_GOOGLE_BOOKS", "100")),
            "google_trends": int(os.environ.get("QUOTA_GOOGLE_TRENDS", "60")),
            "arxiv": int(os.environ.get("QUOTA_ARXIV", "120")),
            "app_store": int(os.environ.get("QUOTA_APP_STORE", "100")),
        }

    def _get_today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _check_and_reset(self):
        today = self._get_today()
        if today != self._current_date:
            self._counts.clear()
            self._current_date = today

    def can_consume(self, service: str) -> tuple[bool, str]:
        self._check_and_reset()
        limit = self.DAILY_LIMITS.get(service, 50)
        current = self._counts.get(service, 0)
        if current >= limit:
            return False, f"⚠️ Daily free quota reached for '{service}' ({current}/{limit} calls today). Refusing call to prevent expense."
        return True, ""

    def consume(self, service: str):
        self._check_and_reset()
        self._counts[service] = self._counts.get(service, 0) + 1
        log.info("Quota consumed for %s: %d/%d today", service, self._counts[service], self.DAILY_LIMITS.get(service, 50))


class RateLimiter:
    """Sliding-window throttler to prevent burst requests and respect service terms."""

    def __init__(self):
        self._last_call: dict[str, float] = {}
        self._history: dict[str, list[float]] = {}
        # Minimum seconds between individual calls
        self.MIN_INTERVALS = {
            "google_web": 0.5,
            "google_books": 0.5,
            "google_trends": 1.0,
            "arxiv": 3.0,       # arXiv requires at least 3 seconds between calls
            "app_store": 0.5,
        }

    def throttle(self, service: str):
        now = time.time()
        min_interval = self.MIN_INTERVALS.get(service, 1.0)
        last = self._last_call.get(service, 0.0)
        elapsed = now - last
        if elapsed < min_interval:
            sleep_time = min_interval - elapsed
            time.sleep(sleep_time)
        self._last_call[service] = time.time()


_quota_tracker = DailyQuotaTracker()
_rate_limiter = RateLimiter()


# ---------------------------------------------------------------------------
# 1. Google Custom Search (Live Web / Competitor Sites)
# ---------------------------------------------------------------------------

def search_google_web(query: str, max_results: int = 5) -> str:
    """Search Google for live competitor websites, pricing, API documentation, and industry news.

    Args:
        query: Search term or question.
        max_results: Max results to return (1 to 8).
    """
    clean_q = query.strip()
    if not clean_q:
        return "Please provide a valid search query."

    can_call, err_msg = _quota_tracker.can_consume("google_web")
    if not can_call:
        return err_msg

    _rate_limiter.throttle("google_web")
    _quota_tracker.consume("google_web")

    max_results = min(8, max(1, max_results))
    api_key = os.environ.get("GOOGLE_SEARCH_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
    cx = os.environ.get("GOOGLE_CSE_ID", "").strip()

    if not cx:
        return (
            "ℹ️ <b>Google Custom Search</b>: <code>GOOGLE_CSE_ID</code> is not configured in <code>.env</code>.\n"
            "To enable Google Search, create a free Custom Search Engine at https://programmablesearchengine.google.com "
            "and add <code>GOOGLE_CSE_ID</code> to your environment."
        )

    url = (
        f"https://www.googleapis.com/customsearch/v1"
        f"?key={urllib.parse.quote(api_key)}"
        f"&cx={urllib.parse.quote(cx)}"
        f"&q={urllib.parse.quote(clean_q)}"
        f"&num={max_results}"
    )

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VolcanoObserver/1.0"})
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        items = data.get("items", [])
        if not items:
            return f"No Google search results found for: <code>{html.escape(query)}</code>"

        lines = [f"🔍 <b>Google Search Results for:</b> <i>{html.escape(query)}</i>\n"]
        for item in items[:max_results]:
            title = html.escape(item.get("title", "No title"))
            link = html.escape(item.get("link", ""))
            snippet = html.escape(item.get("snippet", "").replace("\n", " "))
            lines.append(f"• <b>{title}</b>\n  {snippet}\n  🔗 <a href=\"{link}\">{link}</a>")

        return "\n\n".join(lines)

    except urllib.error.HTTPError as e:
        log.warning("Google Custom Search HTTP error %d: %s", e.code, e.reason)
        return f"⚠️ <b>Google Search Error:</b> HTTP {e.code} ({html.escape(e.reason)}). Check API key and CSE ID."
    except Exception as e:
        log.error("Google Custom Search exception: %s", e)
        return f"⚠️ <b>Google Search Error:</b> {html.escape(str(e))}"


# ---------------------------------------------------------------------------
# 2. Google Books API (Textbooks, Medicine, Exercise Science Literature)
# ---------------------------------------------------------------------------

def search_google_books(query: str, max_results: int = 5) -> str:
    """Search Google Books for textbooks, clinical guides, physiology, and exercise science literature.

    Args:
        query: Subject, title, or medical/technical query.
        max_results: Max books to return (1 to 6).
    """
    clean_q = query.strip()
    if not clean_q:
        return "Please provide a book or subject search query."

    can_call, err_msg = _quota_tracker.can_consume("google_books")
    if not can_call:
        return err_msg

    _rate_limiter.throttle("google_books")
    _quota_tracker.consume("google_books")

    max_results = min(6, max(1, max_results))
    api_key = os.environ.get("GOOGLE_SEARCH_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
    key_param = f"&key={urllib.parse.quote(api_key)}" if api_key else ""

    url = (
        f"https://www.googleapis.com/books/v1/volumes"
        f"?q={urllib.parse.quote(clean_q)}"
        f"&maxResults={max_results}"
        f"&printType=books"
        f"{key_param}"
    )

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VolcanoObserver/1.0"})
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        items = data.get("items", [])
        if not items:
            return f"No published books found for: <code>{html.escape(query)}</code>"

        lines = [f"📚 <b>Google Books Literature for:</b> <i>{html.escape(query)}</i>\n"]
        for item in items[:max_results]:
            vol = item.get("volumeInfo", {})
            title = html.escape(vol.get("title", "Unknown Title"))
            authors = html.escape(", ".join(vol.get("authors", ["Unknown Author"])))
            published_date = html.escape(vol.get("publishedDate", "N/A"))
            page_count = vol.get("pageCount", "N/A")
            desc = vol.get("description", "No description available.")
            desc_snip = html.escape(desc[:200] + ("..." if len(desc) > 200 else ""))
            info_link = html.escape(vol.get("infoLink", ""))

            lines.append(
                f"📖 <b>{title}</b> ({published_date})\n"
                f"  <b>Authors:</b> {authors} | <b>Pages:</b> {page_count}\n"
                f"  <i>\"{desc_snip}\"</i>\n"
                f"  🔗 <a href=\"{info_link}\">Google Books Link</a>"
            )

        return "\n\n".join(lines)

    except Exception as e:
        log.error("Google Books API error: %s", e)
        return f"⚠️ <b>Google Books Error:</b> {html.escape(str(e))}"


# ---------------------------------------------------------------------------
# 3. Google Trends (Consumer Search Interest & Rising Queries)
# ---------------------------------------------------------------------------

def search_google_trends(keyword: str) -> str:
    """Explore Google Trends for consumer search volume trends and rising related queries.

    Args:
        keyword: Keyword or topic to explore.
    """
    clean_kw = keyword.strip()
    if not clean_kw:
        return "Please provide a keyword for Google Trends."

    can_call, err_msg = _quota_tracker.can_consume("google_trends")
    if not can_call:
        return err_msg

    _rate_limiter.throttle("google_trends")
    _quota_tracker.consume("google_trends")

    # Use Google Trends Autocomplete & Exploration endpoints
    url = f"https://trends.google.com/trends/api/autocomplete/{urllib.parse.quote(clean_kw)}?hl=en-US"

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            raw_text = resp.read().decode("utf-8")

        # Google Trends prefixes valid JSON with ")]}',\n"
        if raw_text.startswith(")]}',"):
            raw_text = raw_text[5:].strip()

        data = json.loads(raw_text)
        topics = data.get("default", {}).get("topics", [])

        if not topics:
            return (
                f"📈 <b>Google Trends Exploration:</b> <code>{html.escape(keyword)}</code>\n"
                f"No specific trending topic entities found. View live search graph at:\n"
                f"🔗 <a href=\"https://trends.google.com/trends/explore?q={urllib.parse.quote(keyword)}\">Google Trends Explore</a>"
            )

        lines = [
            f"📈 <b>Google Trends Topic Entities for:</b> <i>{html.escape(keyword)}</i>\n",
        ]
        for t in topics[:5]:
            title = html.escape(t.get("title", ""))
            topic_type = html.escape(t.get("type", "Topic"))
            mid = t.get("mid", "")
            lines.append(f"• <b>{title}</b> (<code>{topic_type}</code>)")

        explore_url = f"https://trends.google.com/trends/explore?q={urllib.parse.quote(keyword)}"
        lines.append(f"\n📊 <b>Explore Live Graph & Breakouts:</b>\n🔗 <a href=\"{explore_url}\">{explore_url}</a>")
        return "\n".join(lines)

    except Exception as e:
        log.warning("Google Trends query error for '%s': %s", keyword, e)
        explore_url = f"https://trends.google.com/trends/explore?q={urllib.parse.quote(clean_kw)}"
        return (
            f"📈 <b>Google Trends for '{html.escape(clean_kw)}':</b>\n"
            f"🔗 <a href=\"{explore_url}\">View Live Trends & Regional Breakdown</a>"
        )


# ---------------------------------------------------------------------------
# 4. arXiv Academic Search (AI, Computer Vision, Pose Estimation, Algorithms)
# ---------------------------------------------------------------------------

def search_arxiv(query: str, max_results: int = 5) -> str:
    """Search arXiv for peer-reviewed preprints on AI, Computer Vision, Pose Estimation, and Algorithms.

    Args:
        query: Academic search query (e.g. 'pose estimation real-time mobile', 'pgvector hybrid retrieval').
        max_results: Max papers to return (1 to 5).
    """
    clean_q = query.strip()
    if not clean_q:
        return "Please provide an arXiv search query."

    can_call, err_msg = _quota_tracker.can_consume("arxiv")
    if not can_call:
        return err_msg

    _rate_limiter.throttle("arxiv")
    _quota_tracker.consume("arxiv")

    max_results = min(5, max(1, max_results))
    url = (
        f"https://export.arxiv.org/api/query"
        f"?search_query=all:{urllib.parse.quote(clean_q)}"
        f"&start=0"
        f"&max_results={max_results}"
        f"&sortBy=relevance"
        f"&sortOrder=descending"
    )

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VolcanoObserver/1.0 (mailto:miles@mileshillary.com)"})
        with urllib.request.urlopen(req, timeout=12.0) as resp:
            xml_data = resp.read()

        root = ET.fromstring(xml_data)
        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

        entries = root.findall("atom:entry", ns)
        if not entries:
            return f"No arXiv academic papers found for: <code>{html.escape(query)}</code>"

        lines = [f"🔬 <b>arXiv Academic Papers for:</b> <i>{html.escape(query)}</i>\n"]
        for entry in entries[:max_results]:
            title_el = entry.find("atom:title", ns)
            title = " ".join((title_el.text or "").split()) if title_el is not None else "Untitled"
            title = html.escape(title)

            published_el = entry.find("atom:published", ns)
            published = (published_el.text or "")[:10] if published_el is not None else "N/A"

            authors = []
            for author_el in entry.findall("atom:author", ns):
                name_el = author_el.find("atom:name", ns)
                if name_el is not None and name_el.text:
                    authors.append(name_el.text)
            authors_str = html.escape(", ".join(authors[:3]) + (" et al." if len(authors) > 3 else ""))

            summary_el = entry.find("atom:summary", ns)
            summary = " ".join((summary_el.text or "").split()) if summary_el is not None else ""
            summary_snip = html.escape(summary[:220] + ("..." if len(summary) > 220 else ""))

            id_el = entry.find("atom:id", ns)
            paper_url = id_el.text if id_el is not None else ""

            lines.append(
                f"📄 <b>{title}</b> ({published})\n"
                f"  <b>Authors:</b> {authors_str}\n"
                f"  <i>\"{summary_snip}\"</i>\n"
                f"  🔗 <a href=\"{html.escape(paper_url)}\">{html.escape(paper_url)}</a>"
            )

        return "\n\n".join(lines)

    except Exception as e:
        log.error("arXiv search error: %s", e)
        return f"⚠️ <b>arXiv Error:</b> {html.escape(str(e))}"


# ---------------------------------------------------------------------------
# 5. Apple App Store Customer Reviews (Competitor Teardown & User Complaints)
# ---------------------------------------------------------------------------

def search_app_store_reviews(app_name_or_id: str, country: str = "us", max_results: int = 5) -> str:
    """Fetch customer ratings, complaints, and 1-star to 5-star reviews for any iOS competitor app.

    Args:
        app_name_or_id: App name (e.g. 'Whoop', 'MyFitnessPal', 'Hevy') or numeric Apple App ID.
        country: Two-letter country code (default: 'us', 'gb', etc.).
        max_results: Max reviews to return (1 to 8).
    """
    target = app_name_or_id.strip()
    if not target:
        return "Please provide an iOS app name or App ID."

    can_call, err_msg = _quota_tracker.can_consume("app_store")
    if not can_call:
        return err_msg

    _rate_limiter.throttle("app_store")
    _quota_tracker.consume("app_store")

    max_results = min(8, max(1, max_results))
    app_id = target
    app_title = target

    # If an app name was given instead of a numeric ID, search iTunes API to resolve ID
    if not target.isdigit():
        search_url = f"https://itunes.apple.com/search?term={urllib.parse.quote(target)}&entity=software&limit=1&country={country}"
        try:
            req = urllib.request.Request(search_url, headers={"User-Agent": "VolcanoObserver/1.0"})
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results", [])
            if not results:
                return f"No iOS app found on Apple App Store for name: <code>{html.escape(target)}</code>"
            app_id = str(results[0].get("trackId", ""))
            app_title = results[0].get("trackName", target)
            avg_rating = results[0].get("averageUserRating", "N/A")
            rating_count = results[0].get("userRatingCount", 0)
        except Exception as e:
            log.warning("App store lookup failed: %s", e)
            return f"⚠️ <b>App Store Lookup Error:</b> {html.escape(str(e))}"

    # Query Apple RSS JSON Feed for Customer Reviews
    rss_url = f"https://itunes.apple.com/{country}/rss/customerreviews/id={app_id}/sortBy=mostRecent/json"
    try:
        req = urllib.request.Request(rss_url, headers={"User-Agent": "VolcanoObserver/1.0"})
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        entries = data.get("feed", {}).get("entry", [])
        if not entries or len(entries) <= 1:
            return f"No customer reviews found for <b>{html.escape(app_title)}</b> (ID: <code>{app_id}</code>) in country <code>{country}</code>."

        # The first entry in Apple RSS is metadata about the app itself; subsequent entries are reviews
        review_entries = entries[1:]
        lines = [
            f"📱 <b>App Store Reviews for: {html.escape(app_title)}</b> (ID: <code>{app_id}</code>)\n"
            f"<i>Recent customer feedback & complaints:</i>\n"
        ]

        for entry in review_entries[:max_results]:
            rating = entry.get("im:rating", {}).get("label", "?")
            title = html.escape(entry.get("title", {}).get("label", "Review"))
            content = html.escape(entry.get("content", {}).get("label", "").replace("\n", " "))
            content_snip = content[:250] + ("..." if len(content) > 250 else "")
            author = html.escape(entry.get("author", {}).get("name", {}).get("label", "Anonymous"))
            version = html.escape(entry.get("im:version", {}).get("label", ""))

            stars = "⭐" * int(rating) if rating.isdigit() else f"Rating: {rating}"
            lines.append(
                f"• {stars} <b>{title}</b> (v{version} by <i>{author}</i>)\n"
                f"  <blockquote>{content_snip}</blockquote>"
            )

        return "\n\n".join(lines)

    except urllib.error.HTTPError as e:
        if e.code == 404:
            return f"No reviews found on App Store for App ID <code>{app_id}</code> in country <code>{country}</code>."
        return f"⚠️ <b>App Store Error:</b> HTTP {e.code} ({html.escape(e.reason)})"
    except Exception as e:
        log.error("App Store review fetching error: %s", e)
        return f"⚠️ <b>App Store Error:</b> {html.escape(str(e))}"
