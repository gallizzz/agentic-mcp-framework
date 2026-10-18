"""Shared helpers for decoding MCP tool results."""

import json
from typing import Any

def mcp_result_text(res: Any) -> str:
    """Extracts the raw text payload from an MCP tool result (content blocks or plain value)."""
    if isinstance(res, list) and res:
        item = res[0]
        return item.get("text", "") if isinstance(item, dict) else getattr(item, "text", str(item))
    return str(res) if res is not None else ""

def parse_mcp_response(res: Any) -> tuple[dict, str]:
    """Parses MCP tool output into (data_dict, raw_text)."""
    if isinstance(res, dict):
        return res, json.dumps(res)

    raw_text = mcp_result_text(res)
    try:
        data = json.loads(raw_text)
        if isinstance(data, dict):
            return data, raw_text
    except (json.JSONDecodeError, TypeError):
        pass
    return {}, raw_text
