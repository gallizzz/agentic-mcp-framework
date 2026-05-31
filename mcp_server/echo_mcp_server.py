from mcp.server.fastmcp import FastMCP

mcp = FastMCP("EchoServer")

@mcp.tool()
def echo_message(message: str) -> str:
    """
    Receives a generated message and echoes it to the standard output.
    Essential tool for printing the agent's reasoning results.
    """
    print(f"\n[TOOL ECHO] The agent said: {message}\n")
    return f"Message '{message}' processed and emitted successfully."

if __name__ == "__main__":
    # The MCP server will run indefinitely, waiting for tool calls from connected clients (agents).
    mcp.run()