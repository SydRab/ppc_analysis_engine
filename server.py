"""
MCP Server Bridge for Cloud Run & Claude Integration
---------------------------------------------------------
Repository: SydRab/ppc_analysis_engine
Description: Fast asynchronous FastAPI server acting as an HTTP-compatible 
             Model Context Protocol (MCP) endpoint for Cloud Run and Claude.
"""

import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(title="PPC Analysis MCP Server")

@app.get("/")
@app.get("/health")
@app.get("/mcp")
async def health_check():
    return {"status": "healthy", "service": "ppc-analysis-mcp"}

@app.post("/")
@app.post("/mcp")
async def handle_mcp_post(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
        
    # Handle incoming tool calls or queries from Claude
    response_payload = {
        "jsonrpc": "2.0",
        "result": {
            "content": [
                {
                    "type": "text", 
                    "text": "Successfully queried PPC keyword pipeline via Cloud Run FastAPI bridge!"
                }
            ]
        },
        "id": body.get("id", 1)
    }
    return JSONResponse(content=response_payload)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
