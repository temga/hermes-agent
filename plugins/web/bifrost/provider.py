"""Bifrost MCP HTTP client — web search provider.

Speaks the MCP Streamable HTTP protocol to the Bifrost gateway's /mcp
endpoint. The gateway proxies NeuralDeep Search (web, telegram, crawl).

Protocol flow (per MCP 2024-11-05 spec):
  1. POST /mcp  — initialize (get protocol version, capabilities)
  2. POST /mcp  — notifications/initialized (202 Accepted, no body)
  3. POST /mcp  — tools/call (execute search/crawl)

Each request carries the virtual key via ``Authorization: Bearer sk-bf-*``.
No session ID is needed — Bifrost is stateless between requests.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List

import requests

from agent.web_search_provider import WebSearchProvider

from ._keyresolver import resolve_bifrost_key

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://router.rove-ai.ru"

# MCP protocol version we speak
_MCP_PROTOCOL = "2024-11-05"


class BifrostMCPClient:
    """Minimal MCP Streamable HTTP client for Bifrost gateway.

    Bifrost prefixes tool names with the MCP client name (e.g.
    ``neuraldeep_search-web_search``). This client auto-discovers the
    prefix via tools/list and resolves short names to full names.
    """

    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        self._base = base_url.rstrip("/")
        self._url = f"{self._base}/mcp"
        self._key = api_key
        self._timeout = timeout
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        self._initialized = False
        self._tool_map: dict[str, str] = {}  # short name → full name

    def _post(self, payload: dict) -> dict:
        resp = requests.post(
            self._url, json=payload, headers=self._headers, timeout=self._timeout
        )
        if resp.status_code == 202:
            # Notification accepted — no body
            return {}
        resp.raise_for_status()
        return resp.json()

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        # Step 1: initialize
        init = self._post({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": _MCP_PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": "hermes-bifrost-web", "version": "1.0"},
            },
        })
        logger.debug("MCP initialize: %s", init.get("result", {}).get("serverInfo"))
        # Step 2: notifications/initialized
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        self._initialized = True
        # Step 3: tools/list — build short→full name map
        self._discover_tools()

    def _discover_tools(self) -> None:
        """Fetch tools/list and build a short-name → full-name map.

        Bifrost prefixes tools as ``<client_name>-<tool_name>``.
        We map both the short name (``web_search``) and the full name
        (``neuraldeep_search-web_search``) to the full name.
        """
        resp = self._post({
            "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {},
        })
        tools = resp.get("result", {}).get("tools", [])
        for t in tools:
            full = t.get("name", "")
            if not full:
                continue
            self._tool_map[full] = full
            # Also map the short name (after last `-`, but only if it
            # doesn't collide with another tool's full name)
            if "-" in full:
                short = full.rsplit("-", 1)[-1]
                self._tool_map.setdefault(short, full)
        logger.debug("MCP tools discovered: %s", list(self._tool_map.values()))

    def call_tool(self, name: str, arguments: dict, request_id: int = 100) -> dict:
        """Call an MCP tool by short or full name.

        Bifrost prefixes tool names (e.g. ``neuraldeep_search-web_search``).
        Pass either the short name (``web_search``) or the full name —
        the client resolves it automatically.
        """
        self._ensure_initialized()
        resolved = self._tool_map.get(name, name)
        return self._post({
            "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
            "params": {"name": resolved, "arguments": arguments},
        })


def _extract_text_from_mcp_result(result: dict) -> str:
    """Extract text content from MCP tools/call result.

    MCP returns content as a list of content blocks:
    {"result": {"content": [{"type": "text", "text": "..."}]}}
    """
    content_list = result.get("result", {}).get("content", [])
    texts = []
    for item in content_list:
        if isinstance(item, dict) and item.get("type") == "text":
            texts.append(item.get("text", ""))
        elif isinstance(item, str):
            texts.append(item)
    return "\n".join(texts)


class BifrostWebSearchProvider(WebSearchProvider):
    """Web search + extract via Bifrost gateway MCP."""

    @property
    def name(self) -> str:
        return "bifrost"

    @property
    def display_name(self) -> str:
        return "Bifrost Gateway (MCP)"

    def get_setup_schema(self) -> dict:
        return {
            "name": "Bifrost Gateway (MCP)",
            "badge": "paid",
            "tag": "web_search, tg_search, crawl via NeuralDeep — through Bifrost MCP",
            "env_vars": [
                {
                    "key": "BIFROST_API_KEY",
                    "prompt": "Bifrost virtual key (sk-bf-*)",
                    "url": "https://router.rove-ai.ru",
                },
            ],
        }

    def is_available(self) -> bool:
        return bool(resolve_bifrost_key())

    def _get_client(self) -> BifrostMCPClient | None:
        key = resolve_bifrost_key()
        if not key:
            return None
        base = os.environ.get("BIFROST_BASE_URL", _DEFAULT_BASE_URL)
        # Strip /v1 suffix if present — /mcp is at the gateway root
        if base.endswith("/v1"):
            base = base[:-3]
        return BifrostMCPClient(base, key)

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return True

    def search(self, query: str, limit: int = 5, **kwargs) -> Dict[str, Any]:
        """Search the web via Bifrost MCP (web_search + tg_search tools).

        Returns {"success": True, "data": {"web": [{title, url, description, position}, ...]}}.
        """
        client = self._get_client()
        if not client:
            logger.warning("Bifrost key not set — Bifrost search unavailable")
            return {"success": False, "error": "Bifrost key not set"}

        results: List[Dict[str, Any]] = []
        lang = kwargs.get("lang", "ru")

        # Web search
        try:
            resp = client.call_tool("web_search", {
                "query": query, "limit": limit, "lang": lang,
            })
            if resp.get("error"):
                logger.error("MCP web_search error: %s", resp["error"])
            else:
                text = _extract_text_from_mcp_result(resp)
                results.extend(_parse_search_results(text))
        except Exception as e:
            logger.error("Bifrost web_search failed: %s", e)

        # Telegram search (bonus — merges TG channels into results)
        try:
            resp2 = client.call_tool("tg_search", {
                "query": query, "limit": min(limit, 5),
            })
            if not resp2.get("error"):
                text2 = _extract_text_from_mcp_result(resp2)
                results.extend(_parse_search_results(text2))
        except Exception as e:
            logger.debug("Bifrost tg_search failed (non-critical): %s", e)

        # Deduplicate by URL
        seen = set()
        unique = []
        for r in results:
            url = r.get("url", "")
            if url and url not in seen:
                seen.add(url)
                unique.append(r)

        # Add position field
        for i, r in enumerate(unique):
            r["position"] = i + 1

        return {
            "success": True,
            "data": {"web": unique[:limit]},
        }

    def extract(self, urls: List[str], char_limit: int = 15000, **kwargs) -> List[Dict[str, Any]]:
        """Extract/crawl content from URLs via Bifrost MCP (crawl tool).

        Returns [{url, title, content, error?}, ...].
        """
        client = self._get_client()
        if not client:
            return [{"url": u, "error": "Bifrost key not set"} for u in urls]

        out: List[Dict[str, Any]] = []
        for url in urls:
            try:
                resp = client.call_tool("crawl", {
                    "url": url, "limit": char_limit,
                })
                if resp.get("error"):
                    out.append({"url": url, "error": str(resp["error"].get("message", "unknown"))})
                else:
                    text = _extract_text_from_mcp_result(resp)
                    out.append({
                        "url": url,
                        "title": _extract_title(text, url),
                        "content": text[:char_limit],
                    })
            except Exception as e:
                out.append({"url": url, "error": str(e)})

        return out


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_search_results(text: str) -> List[Dict[str, Any]]:
    """Parse search results from MCP text output.

    NeuralDeep search returns JSON or formatted text. We try JSON first,
    then fall back to line-based parsing.
    """
    results = []

    # Try parsing as JSON first
    try:
        data = json.loads(text)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", item.get("link", "")),
                        "description": item.get("description", item.get("snippet", item.get("content", ""))),
                    })
        elif isinstance(data, dict) and "results" in data:
            for item in data["results"]:
                if isinstance(item, dict):
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", item.get("link", "")),
                        "description": item.get("description", item.get("snippet", item.get("content", ""))),
                    })
        if results:
            return results
    except (json.JSONDecodeError, TypeError):
        pass

    # Fallback: parse NeuralDeep's formatted text output
    # Format:
    #   [1] Title text here
    #       URL: https://...
    #       description snippet...
    current = {}
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            if current.get("url"):
                results.append(current)
                current = {}
            continue

        # [N] Title line
        m = re.match(r'^\[(\d+)\]\s*(.+)', stripped)
        if m:
            if current.get("url"):
                results.append(current)
            current = {"title": m.group(2).strip(), "url": "", "description": ""}
        elif stripped.startswith("URL:"):
            current["url"] = stripped[4:].strip()
        elif current.get("url") and not current.get("description"):
            current["description"] = stripped
        elif current.get("url") and current.get("description"):
            current["description"] += " " + stripped

    if current.get("url"):
        results.append(current)

    return results


def _extract_title(text: str, fallback_url: str) -> str:
    """Try to extract a title from crawled content."""
    # Look for first markdown heading or <title> tag
    for line in text.split("\n")[:20]:
        line = line.strip()
        if line.startswith("# "):
            return line.lstrip("# ").strip()
        if line.startswith("Title:"):
            return line.split(":", 1)[1].strip()
    # Fallback: first non-empty line
    for line in text.split("\n"):
        line = line.strip()
        if line and len(line) > 5:
            return line[:100]
    return fallback_url
