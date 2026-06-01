# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base

# - PYTHONDONTWRITEBYTECODE: no .pyc files in the image
# - PYTHONUNBUFFERED: stream logs straight to stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Build tools needed for lxml; removed after the wheel build to keep the image small.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for better layer caching.
COPY ai_junkie_updates/requirements.txt ./requirements.txt
# feedparser's sgmllib3k dep fails to build on 3.11; install feedparser without
# deps and vendor sgmllib.py (the same workaround documented in CLAUDE.md).
RUN grep -v '^feedparser' requirements.txt > requirements.core.txt \
    && pip install -r requirements.core.txt \
    && pip install --no-deps "feedparser>=6.0.11,<7.0.0" \
    && SP=$(python -c "import site; print(site.getsitepackages()[0])") \
    && pip download --no-deps --no-build-isolation sgmllib3k -d /tmp/sgml \
    && tar -xzf /tmp/sgml/sgmllib3k-*.tar.gz -C /tmp/sgml \
    && cp /tmp/sgml/sgmllib3k-*/sgmllib.py "$SP/sgmllib.py" \
    && rm -rf /tmp/sgml

# Now drop the build toolchain to slim the runtime image.
RUN apt-get purge -y build-essential && apt-get autoremove -y

# Copy the application source.
COPY ai_junkie_updates ./ai_junkie_updates

# Persisted SQLite database lives here; mount a volume to keep it across restarts.
RUN mkdir -p /app/ai_junkie_updates/storage
VOLUME ["/app/ai_junkie_updates/storage"]

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

# All config comes from AIJU_-prefixed environment variables (see .env.example).
CMD ["python", "-m", "ai_junkie_updates.main"]
