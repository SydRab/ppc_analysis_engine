FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Pinned version + Firestore extra so OAuth sign-ins survive restarts (GOOGLE_ADS_MCP_STORAGE_TYPE=firestore)
RUN pip install --no-cache-dir "google-ads-mcp[firestore]==0.0.6"

ENV PORT=8080
EXPOSE 8080

CMD ["python", "-m", "ads_mcp.server"]
