FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Non-root user for security — but ownership of mounted volumes/disks has to be
# fixed at container START (entrypoint.sh), not just here at build time. Render's
# persistent disks and Docker's anonymous volumes both default to root ownership
# on every fresh mount, which would otherwise block appuser from writing logs/DB.
RUN useradd -m appuser && chown -R appuser:appuser /app
RUN chmod +x entrypoint.sh

VOLUME ["/app/data", "/app/logs"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

# Stays root here on purpose — entrypoint.sh fixes ownership then drops to
# appuser itself before exec-ing uvicorn. See entrypoint.sh for why.
ENTRYPOINT ["/app/entrypoint.sh"]
