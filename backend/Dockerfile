FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY mcp-server/mlit-geospatial-mcp/requirements.txt /tmp/mlit-geospatial-requirements.txt
RUN pip install --no-cache-dir -r /tmp/mlit-geospatial-requirements.txt

COPY backend ./backend
COPY mcp-server ./mcp-server
COPY main.py .

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
