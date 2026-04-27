import hashlib
import os
import shlex
import sys
from pathlib import Path

from dotenv import load_dotenv


REINFOLIB_MCP_COMMAND_ENV = "REINFOLIB_MCP_COMMAND"
REINFOLIB_MCP_TOOL_ENV = "REINFOLIB_MCP_TOOL"
MLIT_DATA_PLATFORM_MCP_COMMAND_ENV = "MLIT_DATA_PLATFORM_MCP_COMMAND"
MLIT_DATA_PLATFORM_MCP_TOOL_ENV = "MLIT_DATA_PLATFORM_MCP_TOOL"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_MODEL_ENV = "OPENAI_MODEL"
LIBRARY_API_KEY_ENV = "LIBRARY_API_KEY"
REINFOLIB_API_KEY_ENV = "REINFOLIB_API_KEY"
MLIT_API_KEY_ENV = "MLIT_API_KEY"
MLIT_DATA_PLATFORM_API_KEY_ENV = "MLIT_DATA_PLATFORM_API_KEY"
MLIT_BASE_URL_ENV = "MLIT_BASE_URL"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_CENTER = {"lat": 35.681236, "lng": 139.767125}
DEFAULT_REINFOLIB_MCP_COMMAND = "python mcp-server/mlit-geospatial-mcp/src/server.py"
DEFAULT_DATA_PLATFORM_MCP_COMMAND = "python mcp-server/mlit-dpf-mcp/src/server.py"

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")


def parse_command(command: str | None) -> list[str] | None:
    if not command:
        return None
    parts = shlex.split(command)
    if parts and parts[0] == "python":
        parts[0] = sys.executable
    return parts


def get_reinfolib_mcp_command() -> list[str] | None:
    return parse_command(os.getenv(REINFOLIB_MCP_COMMAND_ENV, DEFAULT_REINFOLIB_MCP_COMMAND))


def get_data_platform_mcp_command() -> list[str] | None:
    return parse_command(os.getenv(MLIT_DATA_PLATFORM_MCP_COMMAND_ENV, DEFAULT_DATA_PLATFORM_MCP_COMMAND))


def get_reinfolib_configured_tool() -> str | None:
    return os.getenv(REINFOLIB_MCP_TOOL_ENV)


def get_data_platform_configured_tool() -> str | None:
    return os.getenv(MLIT_DATA_PLATFORM_MCP_TOOL_ENV)


def get_configured_tool() -> str | None:
    return get_reinfolib_configured_tool()


def is_openai_configured() -> bool:
    return bool(os.getenv(OPENAI_API_KEY_ENV))


def is_library_api_configured() -> bool:
    return bool(os.getenv(LIBRARY_API_KEY_ENV) or os.getenv(REINFOLIB_API_KEY_ENV))


def is_data_platform_api_configured() -> bool:
    return bool(os.getenv(MLIT_API_KEY_ENV) or os.getenv(MLIT_DATA_PLATFORM_API_KEY_ENV))


def get_library_api_key_fingerprint() -> dict:
    value = os.getenv(LIBRARY_API_KEY_ENV) or os.getenv(REINFOLIB_API_KEY_ENV, "")
    return get_secret_fingerprint(value)


def get_data_platform_api_key_fingerprint() -> dict:
    value = os.getenv(MLIT_API_KEY_ENV) or os.getenv(MLIT_DATA_PLATFORM_API_KEY_ENV, "")
    return get_secret_fingerprint(value)


def get_secret_fingerprint(value: str) -> dict:
    return {
        "present": bool(value),
        "length": len(value),
        "sha256_8": hashlib.sha256(value.encode()).hexdigest()[:8] if value else None,
        "has_space_edges": value != value.strip(),
    }


def get_openai_model() -> str:
    return os.getenv(OPENAI_MODEL_ENV, DEFAULT_OPENAI_MODEL)
