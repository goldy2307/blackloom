FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Non-root user — basic container security hygiene for production
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

VOLUME ["/app/data", "/app/logs"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

WORKDIR /app/api
# Single worker: APScheduler runs in-process. Multiple workers would each run their
# own scheduler and duplicate pipeline runs. See README "Scaling beyond one instance".
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]