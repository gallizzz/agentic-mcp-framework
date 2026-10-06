import logging
import os
import time

# Suppress internal MCP server request info logs
logging.getLogger("mcp").setLevel(logging.WARNING)

try:
    from mcp.server.mcpserver import MCPServer
except ModuleNotFoundError:
    from mcp.server.fastmcp import FastMCP as MCPServer

import json
from pathlib import Path
from typing import Optional

# Set timezone to Rome
os.environ["TZ"] = "Europe/Rome"
if hasattr(time, "tzset"):
    time.tzset()

mcp = MCPServer("VehicleActuatorServer")

STATE_FILE = Path(os.getenv("VEHICLE_STATE_FILE", "/tmp/vehicle_state.json"))

DEFAULT_STATE = {
    "speed": 50,
    "lane": "center",
    "last_action": "INIT",
    "right_lane_free": False,
}


def load_vehicle_state() -> dict:
    if STATE_FILE.is_file():
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return dict(DEFAULT_STATE)


def save_vehicle_state(state: dict) -> None:
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        logging.warning(f"Could not persist vehicle state: {e}")


@mcp.tool()
def execute_vehicle_action(
    action: str, 
    speed_delta: Optional[int] = None, 
    right_lane_free: Optional[bool] = None
) -> str:
    """
    Executes a driving control action on the vehicle actuator in the environment.

    Args:
        action: The command to execute (e.g. 'FASTER', 'SLOWER', 'KEEP', 'IDLE', 'CHANGE_LANE', 'LANE_RIGHT', 'LANE_LEFT', 'STOP').
        speed_delta: Amount of speed change in km/h (optional, default is 20 km/h).
        right_lane_free: Sensor reading indicating whether the right lane is free.
    """
    vehicle_state = load_vehicle_state()
    action_upper = action.strip().upper()
    previous_speed = vehicle_state["speed"]
    delta = int(speed_delta) if speed_delta is not None and speed_delta > 0 else 20

    if right_lane_free is not None:
        vehicle_state["right_lane_free"] = bool(right_lane_free)

    if action_upper == "FASTER":
        vehicle_state["speed"] += delta
    elif action_upper == "SLOWER":
        vehicle_state["speed"] = max(0, vehicle_state["speed"] - delta)
    elif action_upper == "STOP":
        vehicle_state["speed"] = 0
    elif action_upper == "LANE_RIGHT":
        vehicle_state["lane"] = "right"
    elif action_upper == "LANE_LEFT":
        vehicle_state["lane"] = "center"
    elif action_upper == "CHANGE_LANE":
        vehicle_state["lane"] = "right" if vehicle_state["lane"] == "center" else "center"
    elif action_upper in ("KEEP", "IDLE"):
        pass  # Maintains current speed and lane

    vehicle_state["last_action"] = action_upper
    save_vehicle_state(vehicle_state)

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
    vehicle_state = load_vehicle_state()
    return (
        f"Speed: {vehicle_state['speed']} km/h, "
        f"Lane: {vehicle_state['lane']}, "
        f"Right Lane Free: {vehicle_state['right_lane_free']}, "
        f"Last Action: {vehicle_state['last_action']}."
    )


if __name__ == "__main__":
    mcp.run()
