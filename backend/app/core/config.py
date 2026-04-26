import os
import shlex


MLIT_MCP_COMMAND_ENV = "MLIT_MCP_COMMAND"
MLIT_MCP_TOOL_ENV = "MLIT_MCP_TOOL"
DEFAULT_CENTER = {"lat": 35.681236, "lng": 139.767125}


def get_mcp_command() -> list[str] | None:
    command = os.getenv(MLIT_MCP_COMMAND_ENV)
    if not command:
        return None
    return shlex.split(command)


def get_configured_tool() -> str | None:
    return os.getenv(MLIT_MCP_TOOL_ENV)
