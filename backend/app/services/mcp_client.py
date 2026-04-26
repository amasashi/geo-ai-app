import json
import re
import select
import subprocess
import time
from typing import Any

from backend.app.core.config import DEFAULT_CENTER, get_configured_tool, get_mcp_command


def read_mcp_response(
    process: subprocess.Popen[str],
    expected_id: int,
    timeout_seconds: int = 20,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("MCP server process exited before responding.")

        ready, _, _ = select.select([process.stdout], [], [], 0.1)
        if not ready:
            continue

        line = process.stdout.readline()
        if not line:
            continue

        message = json.loads(line)
        if message.get("id") == expected_id:
            if "error" in message:
                raise RuntimeError(json.dumps(message["error"], ensure_ascii=False))
            return message

    raise TimeoutError("Timed out while waiting for the MCP server response.")


def send_mcp_message(
    process: subprocess.Popen[str],
    message: dict[str, Any],
) -> None:
    process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
    process.stdin.flush()


def select_tool(tools: list[dict[str, Any]]) -> dict[str, Any]:
    configured_tool = get_configured_tool()
    if configured_tool:
        for tool in tools:
            if tool.get("name") == configured_tool:
                return tool
        raise RuntimeError(f"Configured MCP tool was not found: {configured_tool}")

    preferred_keywords = [
        "search",
        "multi",
        "land_price",
        "zoning",
        "urban",
        "geo",
    ]
    for keyword in preferred_keywords:
        for tool in tools:
            if keyword in tool.get("name", "").lower():
                return tool

    if not tools:
        raise RuntimeError("No tools are available from the MCP server.")
    return tools[0]


def extract_coordinates(query: str) -> dict[str, float]:
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", query)
    if not match:
        return DEFAULT_CENTER

    first = float(match.group(1))
    second = float(match.group(2))

    if abs(first) <= 90 and abs(second) <= 180:
        return {"lat": first, "lng": second}
    return {"lat": second, "lng": first}


def build_tool_arguments(tool: dict[str, Any], query: str) -> dict[str, Any]:
    schema = tool.get("inputSchema") or {}
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    coordinates = extract_coordinates(query)
    arguments: dict[str, Any] = {}
    first_string_field: str | None = None

    for name, definition in properties.items():
        field_type = definition.get("type")
        lower_name = name.lower()

        if field_type == "string":
            if first_string_field is None:
                first_string_field = name
            if any(
                token in lower_name
                for token in ["query", "keyword", "search", "text", "prompt", "question"]
            ):
                arguments[name] = query
            elif name in required:
                arguments[name] = query
        elif field_type in ["number", "integer"]:
            if any(token in lower_name for token in ["lat", "latitude"]):
                arguments[name] = coordinates["lat"]
            elif any(token in lower_name for token in ["lon", "lng", "longitude"]):
                arguments[name] = coordinates["lng"]
            elif name in required:
                arguments[name] = 0
        elif field_type == "boolean" and name in required:
            arguments[name] = False
        elif field_type == "array" and name in required:
            arguments[name] = []
        elif field_type == "object" and name in required:
            arguments[name] = {}

    if not arguments and first_string_field:
        arguments[first_string_field] = query

    return arguments


def call_mlit_mcp(query: str) -> dict[str, Any]:
    command = get_mcp_command()
    if not command:
        raise RuntimeError("MLIT_MCP_COMMAND is not set.")

    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    try:
        send_mcp_message(
            process,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "geoai-app", "version": "0.1.0"},
                },
            },
        )
        read_mcp_response(process, 1)
        send_mcp_message(
            process,
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
        )
        send_mcp_message(
            process,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        tools_response = read_mcp_response(process, 2)
        tools = tools_response.get("result", {}).get("tools", [])
        tool = select_tool(tools)
        arguments = build_tool_arguments(tool, query)

        send_mcp_message(
            process,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": tool["name"], "arguments": arguments},
            },
        )
        result_response = read_mcp_response(process, 3, timeout_seconds=45)
        return {
            "tool": tool["name"],
            "arguments": arguments,
            "result": result_response.get("result", {}),
        }
    finally:
        process.terminate()


def find_geojson(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if value.get("type") in {"FeatureCollection", "Feature"}:
            return value
        for nested_value in value.values():
            found = find_geojson(nested_value)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_geojson(item)
            if found:
                return found
    elif isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{"):
            try:
                return find_geojson(json.loads(stripped))
            except json.JSONDecodeError:
                return None
    return None


def extract_result_text(result: dict[str, Any]) -> str:
    content = result.get("content", [])
    texts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            texts.append(item.get("text", ""))
    if texts:
        return "\n\n".join(texts)
    return json.dumps(result, ensure_ascii=False, indent=2)
