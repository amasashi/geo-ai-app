from typing import Any

from pydantic import BaseModel


class MlitQuery(BaseModel):
    query: str


class MlitStatus(BaseModel):
    configured: bool
    command_env: str
    tool_env: str


class MlitQueryResult(BaseModel):
    query: str
    tool: str
    arguments: dict[str, Any]
    geojson: dict[str, Any] | None
    text: str
    raw: dict[str, Any]
