from typing import Any

from pydantic import BaseModel


class MlitQuery(BaseModel):
    query: str


class MlitStatus(BaseModel):
    configured: bool
    openai_configured: bool
    providers: dict[str, Any]
    library_api_configured: bool
    data_platform_api_configured: bool
    library_api_env: str


class MlitQueryResult(BaseModel):
    request_id: str
    query: str
    provider: str | None = None
    tool: str
    arguments: dict[str, Any]
    planner: dict[str, Any] | None = None
    geojson: dict[str, Any] | None
    warning: str | None = None
    direct_reinfolib_diagnostics: dict[str, Any] | None = None
    text: str
    raw: dict[str, Any]
