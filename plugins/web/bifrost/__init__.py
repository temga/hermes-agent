"""Bifrost web search backend — MCP client.

Routes web_search, web_extract, and tg_search through the Bifrost
gateway's MCP endpoint (``POST /mcp``). Uses the same ``BIFROST_API_KEY``
(sk-bf-*) as the LLM provider.

The gateway proxies NeuralDeep Search API (web, telegram, crawl) via
a STDIO MCP server. This plugin speaks the MCP Streamable HTTP protocol
to the gateway, which handles the actual search requests.

Capabilities:
  - search(): web + telegram search via MCP tools/call
  - extract(): per-URL crawl via MCP tools/call

Config keys::

    web:
      search_backend: "bifrost"
      extract_backend: "bifrost"
      backend: "bifrost"

Env vars::

    BIFROST_API_KEY=sk-bf-...            # required
    BIFROST_BASE_URL=https://router.rove-ai.ru  # optional gateway URL override
"""

from __future__ import annotations

from .provider import BifrostWebSearchProvider


def register(ctx) -> None:
    """Register the Bifrost web search provider with the plugin context."""
    ctx.register_web_search_provider(BifrostWebSearchProvider())
