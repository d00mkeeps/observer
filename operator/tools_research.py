"""Web Research & Market Intelligence Tool for Volcano Observer.

Enables the agent to search the live web for competitor teardowns,
pricing benchmarks, open-source architectures, and industry API standards.
"""

import re
import urllib.parse
import urllib.request
import logging
import html

log = logging.getLogger("operator.tools.research")


def search_web(query: str, max_results: int = 5) -> str:
    """Search the live web for real-time market data, competitor teardowns, APIs, and docs.

    Args:
        query: Search term or market research question.
        max_results: Max search results to return (capped at 8).
    """
    clean_q = query.strip()
    if not clean_q:
        return "Please provide a search query."

    max_results = min(8, max(1, max_results))
    log.info("Executing web search for: '%s'", clean_q)

    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(clean_q)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12.0) as resp:
            html_text = resp.read().decode("utf-8", errors="ignore")

        # Extract result blocks using regex
        snippets = re.findall(r'<a class="result__snippet[^"]*"[^>]*>(.*?)</a>', html_text, re.DOTALL)
        titles_links = re.findall(r'<a class="result__url"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html_text, re.DOTALL)

        results = []
        if snippets:
            for i in range(min(len(snippets), max_results)):
                snip = re.sub(r"<[^>]+>", " ", snippets[i]).strip()
                snip = html.unescape(" ".join(snip.split()))
                link = titles_links[i][0].strip() if i < len(titles_links) else ""
                if link.startswith("//duckduckgo.com/l/?uddg="):
                    try:
                        actual_url = urllib.parse.unquote(link.split("uddg=")[1].split("&")[0])
                        link = actual_url
                    except Exception:
                        pass
                results.append(f"• {snip}\n  Source: {link}")
        else:
            # Fallback regex if DuckDuckGo layout changes
            blocks = re.findall(r'<div class="result__body">(.*?)</div>', html_text, re.DOTALL)
            for b in blocks[:max_results]:
                clean_b = re.sub(r"<[^>]+>", " ", b).strip()
                clean_b = " ".join(clean_b.split())
                if len(clean_b) > 40:
                    results.append(clean_b[:300])

        if not results:
            return f"No search results found for '{query}'. Try rephrasing your search terms."

        header = f"🔍 <b>Live Web Search Results for:</b> '{query}'\n\n"
        return header + "\n\n".join(results[:max_results])

    except Exception as e:
        log.warning("Web search failed for '%s': %s", query, e)
        return f"Web search encountered an error: {str(e)}"
