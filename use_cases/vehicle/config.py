"""Vehicle toy example: reference use case for the Formal Gate engine."""

from pathlib import Path
import sys
from core.config import UseCaseConfig

USE_CASE_DIR = Path(__file__).resolve().parent
RESOURCES_DIR = USE_CASE_DIR.parents[1] / "resources"

USE_CASE = UseCaseConfig(
    asm_model_name="vehicleEnforcer.asm",
    asm_sources=[RESOURCES_DIR / "models" / "vehicleEnforcer.asm",
                 RESOURCES_DIR / "libraries" / "StandardLibrary.asm"],
    environment_mcp_command=[sys.executable, str(USE_CASE_DIR / "vehicle_mcp_server.py")],
    default_safe_action="IDLE",
    action_mapping={"KEEP": "IDLE"},
    default_monitored_variables={"rightLaneFree": "false"},
    gate_policy="shielding",
    error_policy="fail_safe",
)
