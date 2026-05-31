# AI Junkie Updates — container image
# Single-process async app: 13 collection agents + the intelligence layer +
# interactive Telegram bot + health server, all in one event loop.
FROM python:3.11-slim

# System deps: build tools for lxml/cffi, plus libxml/libxslt headers for lxml.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libxml2-dev libxslt1-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for layer caching.
COPY ai_junkie_updates/requirements.txt ./requirements.txt
# feedparser's sgmllib3k dependency fails to build on Python 3.11, so install
# feedparser without its deps, then install everything else normally.
RUN pip install --no-cache-dir --no-deps feedparser \
    && pip install --no-cache-dir -r requirements.txt

# App code.
COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    AIJU_DATABASE_URL=sqlite+aiosqlite:///storage/aiju.db \
    AIJU_HEALTH_CHECK_PORT=8585

EXPOSE 8585

# Container healthcheck hits the liveness endpoint.
HEALTHCHECK --interval=60s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8585/health',timeout=5).status==200 else 1)" || exit 1

CMD ["python", "-m", "ai_junkie_updates.main"]
