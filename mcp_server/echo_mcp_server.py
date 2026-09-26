import logging
import os
import time

# Suppress internal MCP server request info logs
logging.getLogger("mcp").setLevel(logging.WARNING)

try:
    from mcp.server.mcpserver import MCPServer
except ModuleNotFoundError:
    from mcp.server.fastmcp import FastMCP as MCPServer

# Set timezone to Rome
os.environ["TZ"] = "Europe/Rome"
if hasattr(time, "tzset"):
    time.tzset()

mcp = MCPServer("EchoServer")

@mcp.tool()
def echo_message(message: str) -> str:
    """
    Receives a generated message and echoes it to the standard output.
    """
    
    print(f"\n[{time.strftime('%X')}] [TOOL ECHO] The agent said: {message}\n")
    return f"Message '{message}' processed and emitted successfully."

if __name__ == "__main__":
    # The MCP server will run indefinitely, waiting for tool calls from connected clients (agents).
    mcp.run()