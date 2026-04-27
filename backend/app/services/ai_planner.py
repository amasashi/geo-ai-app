import json
from typing import Any

from openai import OpenAI, OpenAIError
from pydantic import BaseModel, Field

from backend.app.core.config import get_openai_model, is_openai_configured
from backend.app.services.mcp_client import build_tool_arguments, select_tool


class McpToolPlan(BaseModel):
    provider_name: str = Field(default="reinfolib", description="MCP provider name to call")
    tool_name: str = Field(description="MCP tool name to call")
    arguments_json: str = Field(description="JSON object string for the selected MCP tool arguments")
    reasoning_summary: str = Field(description="Short Japanese explanation of the choice")
    needs_clarification: bool = Field(description="Whether user input is too ambiguous")
    clarification_question: str | None = Field(description="Question to ask if clarification is needed")

    @property
    def arguments(self) -> dict[str, Any]:
        value = json.loads(self.arguments_json)
        if not isinstance(value, dict):
            raise ValueError("arguments_json must be a JSON object.")
        return value


def summarize_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": tool.get("name"),
            "description": tool.get("description", ""),
            "inputSchema": tool.get("inputSchema", {}),
        }
        for tool in tools
    ]


def summarize_providers(providers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": provider["name"],
            "description": provider.get("description", ""),
            "tools": summarize_tools(provider.get("tools", [])),
        }
        for provider in providers
    ]


def choose_heuristic_provider(query: str, providers: list[dict[str, Any]]) -> dict[str, Any]:
    lower_query = query.lower()
    reinfolib_tokens = [
        "地価",
        "地下公示",
        "用途地域",
        "都市計画",
        "区域区分",
        "立地適正化",
        "不動産",
    ]
    preferred_name = "reinfolib" if any(token in query for token in reinfolib_tokens) else "data_platform"
    if "データプラットフォーム" in query or "data platform" in lower_query:
        preferred_name = "data_platform"

    for provider in providers:
        if provider.get("name") == preferred_name and provider.get("tools"):
            return provider

    for provider in providers:
        if provider.get("tools"):
            return provider

    raise RuntimeError("No MCP tools are available from configured providers.")


def heuristic_plan(query: str, tools: list[dict[str, Any]], provider_name: str = "reinfolib") -> McpToolPlan:
    tool = select_tool(tools)
    return McpToolPlan(
        provider_name=provider_name,
        tool_name=tool["name"],
        arguments_json=json.dumps(build_tool_arguments(tool, query), ensure_ascii=False),
        reasoning_summary="OpenAI APIが未設定のため、既存のヒューリスティックでMCPツールを選択しました。",
        needs_clarification=False,
        clarification_question=None,
    )


def heuristic_provider_plan(query: str, providers: list[dict[str, Any]]) -> McpToolPlan:
    provider = choose_heuristic_provider(query, providers)
    plan = heuristic_plan(query, provider.get("tools", []), provider_name=provider["name"])
    plan.reasoning_summary = (
        "OpenAI APIが未設定または利用できないため、既存のヒューリスティックで"
        f"{provider['name']} のMCPツールを選択しました。"
    )
    return plan


def create_mcp_tool_plan(query: str, tools: list[dict[str, Any]]) -> McpToolPlan:
    if not is_openai_configured():
        return heuristic_plan(query, tools)

    client = OpenAI()
    try:
        response = client.responses.parse(
            model=get_openai_model(),
            input=[
                {
                    "role": "system",
                    "content": (
                        "あなたは地理空間データ取得アプリのMCPツールプランナーです。"
                        "ユーザーの自然言語クエリとMCP tools/listの結果を読み、"
                        "最適なMCPツール名と引数を決めてください。"
                        "引数は必ず選択ツールのinputSchemaに合わせ、arguments_jsonにJSONオブジェクト文字列として入れます。"
                        "地図表示向けに、可能ならGeoJSONや位置情報が返りやすいツールを選びます。"
                        "save_file引数があるツールでは、Web地図表示用なので必ず save_file=false を指定し、"
                        "ファイル保存の確認をユーザーに質問してはいけません。"
                        "曖昧すぎて実行できない場合のみ needs_clarification を true にします。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "user_query": query,
                            "available_tools": summarize_tools(tools),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            text_format=McpToolPlan,
        )
    except OpenAIError as exc:
        plan = heuristic_plan(query, tools)
        plan.reasoning_summary = (
            "OpenAI API呼び出しに失敗したため、ヒューリスティックでMCPツールを選択しました。"
            f" OpenAI error: {exc.__class__.__name__}"
        )
        return plan

    plan = response.output_parsed
    if plan is None:
        return heuristic_plan(query, tools)
    return plan


def create_mcp_provider_plan(query: str, providers: list[dict[str, Any]]) -> McpToolPlan:
    if not is_openai_configured():
        return heuristic_provider_plan(query, providers)

    client = OpenAI()
    try:
        response = client.responses.parse(
            model=get_openai_model(),
            input=[
                {
                    "role": "system",
                    "content": (
                        "あなたは地理空間データ取得アプリのMCPプロバイダ兼ツールプランナーです。"
                        "ユーザーの自然言語クエリとMCP providers/tools/listの結果を読み、"
                        "最適なprovider_name、tool_name、引数を決めてください。"
                        "provider_nameは必ず提示されたprovider nameから選びます。"
                        "reinfolibは不動産情報ライブラリ向けで、地価公示、用途地域、都市計画区域などに強いです。"
                        "data_platformは国土交通データプラットフォーム向けで、横断検索、道路、橋梁、河川、港湾、災害、"
                        "国土交通DP上のデータ検索やダウンロード候補取得に使います。"
                        "引数は必ず選択ツールのinputSchemaに合わせ、arguments_jsonにJSONオブジェクト文字列として入れます。"
                        "地図表示向けに、位置検索ツールがある場合は中心座標と半径を使ってください。"
                        "save_file引数があるツールでは、Web地図表示用なので必ず save_file=false を指定し、"
                        "ファイル保存の確認をユーザーに質問してはいけません。"
                        "曖昧すぎて実行できない場合のみ needs_clarification を true にします。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "user_query": query,
                            "available_providers": summarize_providers(providers),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            text_format=McpToolPlan,
        )
    except OpenAIError as exc:
        plan = heuristic_provider_plan(query, providers)
        plan.reasoning_summary = (
            "OpenAI API呼び出しに失敗したため、ヒューリスティックでMCPプロバイダとツールを選択しました。"
            f" OpenAI error: {exc.__class__.__name__}"
        )
        return plan

    plan = response.output_parsed
    if plan is None:
        return heuristic_provider_plan(query, providers)
    return plan
