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

mcp = MCPServer("VehicleActuatorServer")

# Simulated state of the vehicle in the environment
vehicle_state = {
    "speed": 50,
    "lane": "center",
    "last_action": "INIT",
}


@mcp.tool()
def execute_vehicle_action(action: str) -> str:
    """
    Executes a driving control action on the vehicle actuator in the environment.

    Args:
        action: The command to execute (e.g. 'FASTER', 'SLOWER', 'KEEP', 'CHANGE_LANE').
    """
    action_upper = action.strip().upper()
    previous_speed = vehicle_state["speed"]

    if action_upper == "FASTER":
        vehicle_state["speed"] += 20
    elif action_upper == "SLOWER":
        vehicle_state["speed"] = max(0, vehicle_state["speed"] - 20)
    elif action_upper == "STOP":
        vehicle_state["speed"] = 0
    elif action_upper == "CHANGE_LANE":
        vehicle_state["lane"] = "right" if vehicle_state["lane"] == "center" else "center"

    vehicle_state["last_action"] = action_upper

    timestamp = time.strftime('%X')
    print(f"\n[{timestamp}] 🚗 [VEHICLE ACTUATOR] Executed: '{action_upper}' | Speed: {previous_speed} -> {vehicle_state['speed']} km/h | Lane: {vehicle_state['lane']}\n")

    return (
        f"Vehicle action '{action_upper}' successfully executed. "
        f"New speed: {vehicle_state['speed']} km/h, Lane: {vehicle_state['lane']}."
    )


@mcp.tool()
def get_vehicle_telemetry() -> str:
    """
    Returns the current vehicle telemetry and sensory status.
    """
    return (
        f"Speed: {vehicle_state['speed']} km/h, "
        f"Lane: {vehicle_state['lane']}, "
        f"Last Action: {vehicle_state['last_action']}."
    )


if __name__ == "__main__":
    mcp.run()
