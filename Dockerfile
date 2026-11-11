# ====================================================================
# Cloud Run Deployment Container for Claude MCP Integration
# Repository: SydRab/ppc_analysis_engine
# Description: Packages the Python environment and MCP server to run 
#              as a serverless web service on Google Cloud Run, enabling 
#              real-time AI-driven queries to your Google Ads MCC data.
# ====================================================================

FROM python:3.10-slim

WORKDIR /app

# Install project dependencies (including google-ads and mcp SDK)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy repository source code
COPY . .

# Cloud Run web service port binding
EXPOSE 8080

# Run the MCP server entry point
CMD ["python", "server.py"]
