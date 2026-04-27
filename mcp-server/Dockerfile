FROM python:3.11-slim

WORKDIR /app

COPY mcp-server/mlit-geospatial-mcp/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mcp-server/mlit-geospatial-mcp .

CMD ["python", "src/server.py"]
