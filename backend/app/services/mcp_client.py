import json
import logging
import re
import select
import subprocess
import time
from typing import Any

from backend.app.core.config import (
    DEFAULT_CENTER,
    get_data_platform_configured_tool,
    get_data_platform_mcp_command,
    get_reinfolib_configured_tool,
    get_reinfolib_mcp_command,
)

logger = logging.getLogger(__name__)


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


def read_available_stderr(process: subprocess.Popen[str], timeout_seconds: float = 0.5) -> str:
    if process.stderr is None:
        return ""

    deadline = time.monotonic() + timeout_seconds
    lines = []
    while time.monotonic() < deadline:
        ready, _, _ = select.select([process.stderr], [], [], 0.05)
        if not ready:
            continue
        line = process.stderr.readline()
        if not line:
            break
        lines.append(line.rstrip())
    return "\n".join(lines)


MCP_PROVIDERS = {
    "reinfolib": {
        "description": "不動産情報ライブラリ。地価公示、用途地域、都市計画区域など。",
        "command_getter": get_reinfolib_mcp_command,
        "tool_getter": get_reinfolib_configured_tool,
    },
    "data_platform": {
        "description": "国土交通データプラットフォーム。国土交通DPの横断検索、位置検索、データ詳細、ダウンロードURL取得など。",
        "command_getter": get_data_platform_mcp_command,
        "tool_getter": get_data_platform_configured_tool,
    },
}


class InternalMcpPlan:
    def __init__(self, tool_name: str, reason: str) -> None:
        self.tool_name = tool_name
        self.reason = reason

    def model_dump(self) -> dict[str, Any]:
        return {"internal": True, "tool_name": self.tool_name, "reason": self.reason}


def select_tool(tools: list[dict[str, Any]], configured_tool: str | None = None) -> dict[str, Any]:
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


def infer_target_apis(query: str) -> list[int]:
    api_keywords = [
        (["地価公示", "地下公示", "公示地価", "地価調査"], 3),
        (["都市計画区域", "区域区分"], 4),
        (["用途地域"], 5),
        (["立地適正化"], 6),
        (["駅別乗降客", "乗降客", "乗降者"], 15),
        (["洪水"], 26),
        (["津波"], 28),
        (["土砂災害"], 29),
        (["人口集中", "DID"], 30),
    ]
    return [api_id for keywords, api_id in api_keywords if any(keyword in query for keyword in keywords)]


def normalize_tool_arguments(tool: dict[str, Any], query: str, arguments: dict[str, Any]) -> dict[str, Any]:
    schema = tool.get("inputSchema") or tool.get("input_schema") or {}
    properties = schema.get("properties") or {}
    normalized = dict(arguments)
    tool_name = str(tool.get("name", "")).lower()

    if ("save_file" in properties or "multi_api" in tool_name) and normalized.get("save_file") is None:
        normalized["save_file"] = False

    if ("target_apis" in properties or "multi_api" in tool_name) and not normalized.get("target_apis"):
        normalized["target_apis"] = infer_target_apis(query)

    return normalized


def is_save_file_clarification(question: str | None) -> bool:
    if not question:
        return False
    return "保存" in question and ("ファイル" in question or "save_file" in question)


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

    return normalize_tool_arguments(tool, query, arguments)


def open_mcp_process(command: list[str], provider_name: str, request_id: str) -> subprocess.Popen[str]:
    logger.info(
        "Starting MCP process request_id=%s provider=%s command=%s",
        request_id,
        provider_name,
        command[0],
    )
    return subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )


def initialize_mcp_session(process: subprocess.Popen[str], provider_name: str, request_id: str) -> None:
    logger.info("Initializing MCP session request_id=%s provider=%s", request_id, provider_name)
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


def list_mcp_tools(provider_name: str, request_id: str) -> dict[str, Any]:
    provider = MCP_PROVIDERS[provider_name]
    command = provider["command_getter"]()
    if not command:
        return {"name": provider_name, "description": provider["description"], "tools": [], "configured": False}

    process = open_mcp_process(command, provider_name, request_id)
    try:
        initialize_mcp_session(process, provider_name, request_id)
        send_mcp_message(
            process,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        tools_response = read_mcp_response(process, 2)
        tools = tools_response.get("result", {}).get("tools", [])
        configured_tool = provider["tool_getter"]()
        if configured_tool:
            tools = [tool for tool in tools if tool.get("name") == configured_tool]
        logger.info(
            "MCP tools listed request_id=%s provider=%s tool_count=%s tools=%s configured_tool=%s",
            request_id,
            provider_name,
            len(tools),
            [tool.get("name") for tool in tools],
            configured_tool,
        )
        return {
            "name": provider_name,
            "description": provider["description"],
            "tools": tools,
            "configured": True,
            "configured_tool": configured_tool,
        }
    finally:
        process.terminate()
        logger.info("MCP list process terminated request_id=%s provider=%s", request_id, provider_name)


def list_configured_providers(request_id: str) -> list[dict[str, Any]]:
    providers = []
    for provider_name in MCP_PROVIDERS:
        try:
            providers.append(list_mcp_tools(provider_name, request_id))
        except Exception as exc:
            logger.exception(
                "MCP provider tools/list failed request_id=%s provider=%s error=%s",
                request_id,
                provider_name,
                exc,
            )
            providers.append(
                {
                    "name": provider_name,
                    "description": MCP_PROVIDERS[provider_name]["description"],
                    "tools": [],
                    "configured": False,
                    "error": str(exc),
                }
            )
    return providers


def get_provider_tool(provider: dict[str, Any], tool_name: str) -> dict[str, Any] | None:
    return next((candidate for candidate in provider.get("tools", []) if candidate.get("name") == tool_name), None)


def call_selected_mcp_tool(
    provider_name: str,
    tool: dict[str, Any],
    arguments: dict[str, Any],
    plan: Any,
    request_id: str,
) -> dict[str, Any]:
    provider = MCP_PROVIDERS[provider_name]
    command = provider["command_getter"]()
    if not command:
        raise RuntimeError(f"{provider_name} MCP command is not set.")

    process = open_mcp_process(command, provider_name, request_id)

    try:
        initialize_mcp_session(process, provider_name, request_id)
        logger.info(
            "Calling MCP tool request_id=%s provider=%s tool=%s arguments=%s",
            request_id,
            provider_name,
            tool["name"],
            arguments,
        )
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
        diagnostics = read_available_stderr(process)
        result = result_response.get("result", {})
        content = result.get("content", []) if isinstance(result, dict) else []
        logger.info(
            "MCP tool returned request_id=%s provider=%s tool=%s is_error=%s content_items=%s diagnostics_present=%s",
            request_id,
            provider_name,
            tool["name"],
            result.get("isError") if isinstance(result, dict) else None,
            len(content) if isinstance(content, list) else 0,
            bool(diagnostics),
        )
        if diagnostics:
            logger.warning(
                "MCP diagnostics request_id=%s provider=%s diagnostics=%s",
                request_id,
                provider_name,
                diagnostics[-4000:],
            )
        return {
            "provider": provider_name,
            "tool": tool["name"],
            "arguments": arguments,
            "planner": plan.model_dump(),
            "diagnostics": diagnostics,
            "result": result,
        }
    finally:
        process.terminate()
        logger.info("MCP tool process terminated request_id=%s provider=%s", request_id, provider_name)


def call_mcp_tool_by_name(
    provider_name: str,
    tool_name: str,
    arguments: dict[str, Any],
    request_id: str,
    reason: str,
) -> dict[str, Any]:
    return call_selected_mcp_tool(
        provider_name,
        {"name": tool_name},
        arguments,
        InternalMcpPlan(tool_name, reason),
        request_id,
    )


def call_mlit_mcp(query: str, request_id: str | None = None) -> dict[str, Any]:
    request_id = request_id or "-"
    providers = list_configured_providers(request_id)
    available_providers = [provider for provider in providers if provider.get("tools")]
    if not available_providers:
        raise RuntimeError("No MCP tools are available from configured providers.")

    from backend.app.services.ai_planner import create_mcp_provider_plan

    plan = create_mcp_provider_plan(query, available_providers)
    logger.info(
        "MCP planner result request_id=%s provider=%s tool=%s needs_clarification=%s reasoning=%s",
        request_id,
        plan.provider_name,
        plan.tool_name,
        plan.needs_clarification,
        plan.reasoning_summary,
    )
    if plan.needs_clarification:
        if is_save_file_clarification(plan.clarification_question):
            logger.info(
                "Ignoring save_file clarification for web map request_id=%s question=%s",
                request_id,
                plan.clarification_question,
            )
            plan.needs_clarification = False
        else:
            logger.warning(
                "MCP planner needs clarification request_id=%s question=%s",
                request_id,
                plan.clarification_question,
            )
            raise RuntimeError(plan.clarification_question or "Query needs clarification.")

    provider = next((item for item in available_providers if item.get("name") == plan.provider_name), None)
    if provider is None:
        raise RuntimeError(f"Planner selected an unavailable MCP provider: {plan.provider_name}")

    tool = get_provider_tool(provider, plan.tool_name)
    if tool is None:
        raise RuntimeError(f"Planner selected an unavailable MCP tool: {plan.provider_name}/{plan.tool_name}")

    arguments = normalize_tool_arguments(tool, query, plan.arguments)
    return call_selected_mcp_tool(provider["name"], tool, arguments, plan, request_id)


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
