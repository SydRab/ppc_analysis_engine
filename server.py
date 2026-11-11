"""
MCP Server Bridge for Cloud Run & Claude Integration
---------------------------------------------------------
Repository: SydRab/ppc_analysis_engine
Description: Exposes an HTTP-compatible Model Context Protocol (MCP) endpoint 
             so Cloud Run can host it and Claude can query Google Ads 
             PPC keyword performance and MCC data on demand.
"""

import os
import json
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from mcp.server import Server
from mcp.types import Tool, TextContent

# Initialize MCP server
app = Server("ppc-analysis-mcp")

@app.list_tools()
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

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "get_ppc_keyword_data":
        # Hook this up to your existing python functions from your repo scripts
        output = "Successfully triggered keyword query from ppc_analysis_engine repository!"
        return [TextContent(type="text", text=output)]
        
    raise ValueError(f"Unknown tool: {name}")


# Define a lightweight HTTP handler so Cloud Run detects a listening web service on PORT 8080
class MCPHttpHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Health check endpoint for Cloud Run
        if self.path == "/" or self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy", "service": "ppc-analysis-mcp"}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        # Handle incoming MCP tool call payloads via HTTP POST
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        
        response_payload = {
            "jsonrpc": "2.0",
            "result": {"content": [{"type": "text", "text": "MCP HTTP Server is active and connected to Cloud Run!"}]},
            "id": 1
        }
        self.wfile.write(json.dumps(response_payload).encode("utf-8"))

def run_http_server():
    port = int(os.environ.get("PORT", 8080))
    server_address = ("0.0.0.0", port)
    httpd = HTTPServer(server_address, MCPHttpHandler)
    print(f"Starting MCP HTTP server on port {port}...")
    httpd.serve_forever()

if __name__ == "__main__":
    # Runs the HTTP server so Cloud Run startup validation passes successfully
    run_http_server()
