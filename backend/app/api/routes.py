from fastapi import APIRouter, HTTPException

from backend.app.core.config import (
    MLIT_MCP_COMMAND_ENV,
    MLIT_MCP_TOOL_ENV,
    get_mcp_command,
)
from backend.app.schemas import MlitQuery
from backend.app.services.mcp_client import call_mlit_mcp, extract_result_text, find_geojson

router = APIRouter()


@router.get("/")
def read_root():
    return {"message": "Hello GeoAI"}


@router.get("/health")
def health_check():
    return {"status": "ok", "app": "geoai-app"}


@router.get("/api/mlit/status")
def get_mlit_status():
    return {
        "configured": get_mcp_command() is not None,
        "command_env": MLIT_MCP_COMMAND_ENV,
        "tool_env": MLIT_MCP_TOOL_ENV,
    }


@router.post("/api/mlit/query")
def query_mlit_data(payload: MlitQuery):
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query is required.")

    try:
        mcp_response = call_mlit_mcp(query)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    result = mcp_response["result"]
    geojson = find_geojson(result)

    return {
        "query": query,
        "tool": mcp_response["tool"],
        "arguments": mcp_response["arguments"],
        "geojson": geojson,
        "text": extract_result_text(result),
        "raw": result,
    }
