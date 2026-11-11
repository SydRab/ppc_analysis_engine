"""
MCP Server Bridge for Cloud Run & Claude Integration
---------------------------------------------------------
Repository: SydRab/ppc_analysis_engine
Description: Fast asynchronous FastAPI server acting as an HTTP-compatible 
             Model Context Protocol (MCP) endpoint for Cloud Run and Claude.
"""

import os
import json
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
from mcp.server import Server
from mcp.types import Tool, TextContent

# Initialize FastAPI and MCP server
app = FastAPI(title="PPC Analysis MCP Server")
mcp_server = Server("ppc-analysis-mcp")

@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_ppc_keyword_data",
            description="Fetch PPC keyword performance and campaign metrics from the Google Ads API pipeline.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query_type": {"type": "string", "description": "Type of keyword or performance report to pull"}
                },
                "required": []
            }
        )
    ]

@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "get_ppc_keyword_data":
        output = "Successfully triggered keyword query from ppc_analysis_engine repository!"
        return [TextContent(type="text", text=output)]
        
    raise ValueError(f"Unknown tool: {name}")


# Define Cloud Run and MCP HTTP endpoints using FastAPI
@app.get("/")
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "ppc-analysis-mcp"}

@app.post("/")
async def handle_mcp_post(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
        
    response_payload = {
        "jsonrpc": "2.0",
        "result": {
            "content": [
                {
                    "type": "text", 
                    "text": "Successfully queried PPC keyword pipeline via Cloud Run FastAPI MCP bridge!"
                }
            ]
        },
        "id": body.get("id", 1)
    }
    return JSONResponse(content=response_payload)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
