"""
MCP Server Bridge for Cloud Run & Claude Integration
---------------------------------------------------------
Repository: SydRab/ppc_analysis_engine
Description: Secure FastAPI MCP server requiring an API key header for Claude.
"""

import os
from fastapi import FastAPI, Request, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(title="PPC Analysis MCP Server")
security = HTTPBearer()

# Set a shared secret token in your Cloud Run environment variables (e.g., CLAUDE_MCP_SECRET)
EXPECTED_TOKEN = os.environ.get("CLAUDE_MCP_SECRET", "your-secure-default-token-here")

def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    if credentials.credentials != EXPECTED_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid authorization token")
    return credentials.credentials

@app.get("/")
@app.get("/health")
@app.get("/mcp")
async def health_check():
    return {"status": "healthy", "service": "ppc-analysis-mcp"}

@app.post("/")
@app.post("/mcp")
async def handle_mcp_post(request: Request, token: str = Security(verify_token)):
    try:
        body = await request.json()
    except Exception:
        body = {}
        
    # Hook this up to your Google Ads API execution pipeline here
    response_payload = {
        "jsonrpc": "2.0",
        "result": {
            "content": [
                {
                    "type": "text", 
                    "text": "Successfully authenticated and queried Google Ads MCC pipeline!"
                }
            ]
        },
        "id": body.get("id", 1)
    }
    return JSONResponse(content=response_payload)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
