"""Vehicle toy example: reference use case for the Formal Gate engine."""

from pathlib import Path
import sys
from core.config import UseCaseConfig

USE_CASE_DIR = Path(__file__).resolve().parent

USE_CASE = UseCaseConfig(
    asm_model_name="SafetyEnforcerModel.asm",
    environment_mcp_command=[sys.executable, str(USE_CASE_DIR / "vehicle_mcp_server.py")],
    default_safe_action="IDLE",
    action_mapping={"KEEP": "IDLE"},
    default_monitored_variables={"rightLaneFree": "false"},
    gate_policy="shielding",
    error_policy="fail_safe",
)
