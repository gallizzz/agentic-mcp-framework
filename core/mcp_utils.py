"""Shared helper for decoding MCP tool results."""

import json

def parse_mcp_response(raw: str) -> dict:
    """Parses the text of an MCP tool result; anything but a JSON object gives an empty dict."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}
