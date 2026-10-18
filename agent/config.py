"""Central configuration constants for the Formal Gate Agent framework."""

import sys

# Name of the ASM model registered on AsmetaS-web-service
ASMETA_MODEL_NAME = "SafetyEnforcerModel.asm"

# MCP server execution commands (stdio)
ASMETAS_MCP_COMMAND = [sys.executable, "mcp_server/asmetas/asmetas_mcp_server.py"]
ENVIRONMENT_MCP_COMMAND = [sys.executable, "mcp_server/vehicle/vehicle_mcp_server.py"]

# Maps candidate environment actions to ASM model rule actions
ACTION_MAPPING = {
    "KEEP": "IDLE",
}

# Default values for monitored sensor/probe variables if not provided
DEFAULT_MONITORED_VARIABLES = {
    "rightLaneFree": "false",
}

# policy: "shielding" (force sanitised action) or "replan" (send feedback back to LLM)
GATE_POLICY = "shielding"

# error_policy: "fail_safe" (execute DEFAULT_SAFE_ACTION on gate error) or "fail_stop" (abort turn)
ERROR_POLICY = "fail_safe"

# Safe fallback action when fail_safe is triggered.
DEFAULT_SAFE_ACTION = "IDLE"

# Maximum re-planning iterations before terminating turn
MAX_RETRIES = 3
