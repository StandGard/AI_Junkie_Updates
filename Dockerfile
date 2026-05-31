# =============================================================
# AI Junkie Updates — runtime image
# =============================================================
# Long-running poller: collects from 13 sources, scores via Claude,
# delivers to Telegram. Runs python -m ai_junkie_updates.main forever.
#
# Build:  docker build -t ai-junkie-updates .
# Run:    docker run --env-file ai_junkie_updates/.env \
#                    -v aiju_storage:/app/ai_junkie_updates/storage \
#                    ai-junkie-updates
# =============================================================
FROM python:3.11-slim

# Faster, cleaner Python in containers.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# --- Dependencies (own layer for build-cache reuse) ----------------------
# Copy only requirements first so dependency installs are cached unless the
# requirements file itself changes.
COPY ai_junkie_updates/requirements.txt ./requirements.txt

# --ignore-installed mirrors scripts/setup_env.sh: avoids pip aborting when it
# tries to replace a distro-managed package whose RECORD file is missing.
RUN pip install --ignore-installed -r requirements.txt \
    # Workaround #1 (CLAUDE.md): feedparser needs the stdlib-style 'sgmllib'
    # module, which sgmllib3k does not reliably expose on Python 3.11. If the
    # import is missing, extract the single sgmllib.py from the source tarball.
    && if ! python -c "import sgmllib" >/dev/null 2>&1; then \
         SP="$(python -c 'import site; print(site.getsitepackages()[0])')"; \
         TMP="$(mktemp -d)"; \
         pip download sgmllib3k --no-binary :all: --no-deps -d "$TMP"; \
         tar xzf "$TMP"/sgmllib3k-*.tar.gz -C "$TMP"; \
         cp "$TMP"/sgmllib3k-*/sgmllib.py "$SP/sgmllib.py"; \
         rm -rf "$TMP"; \
       fi \
    # Workaround #2 (CLAUDE.md): python-telegram-bot -> cryptography needs a
    # working cffi backend; install it explicitly if missing.
    && if ! python -c "import _cffi_backend" >/dev/null 2>&1; then \
         pip install --ignore-installed cffi cryptography; \
       fi

# --- Application code -----------------------------------------------------
COPY ai_junkie_updates/ ./ai_junkie_updates/
COPY tests/ ./tests/

# Persist the SQLite database outside the image layer.
VOLUME ["/app/ai_junkie_updates/storage"]

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/ai_junkie_updates/storage \
    && chown -R appuser:appuser /app
USER appuser

# Fail fast at build time if imports are broken; offline test stays runnable
# inside the container via:  docker run ... python tests/test_pipeline_offline.py
RUN python -c "import ai_junkie_updates.main; print('image imports OK')"

# Default command: run the system. Requires credentials via env (see .env.example).
CMD ["python", "-m", "ai_junkie_updates.main"]
