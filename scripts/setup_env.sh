#!/usr/bin/env bash
# =============================================================
# AI Junkie Updates — environment setup
# =============================================================
# Installs dependencies and applies the known build workarounds
# (see CLAUDE.md "Known Issues"). Idempotent — safe to re-run.
#
#   bash scripts/setup_env.sh
# =============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> Ensuring pip is available"
python -m ensurepip --upgrade >/dev/null 2>&1 || true

echo "==> Installing requirements"
# --ignore-installed avoids pip aborting when it tries to upgrade a
# Debian-managed system package whose RECORD file is missing, e.g.:
#   "ERROR: Cannot uninstall PyYAML 6.0.1, RECORD file not found"
python -m pip install --ignore-installed -r ai_junkie_updates/requirements.txt

# ---- Workaround #1: feedparser needs the stdlib-style 'sgmllib' module, but
#      its dependency sgmllib3k can fail to expose it on Python 3.11. If the
#      import is missing, extract the single sgmllib.py from the source tarball
#      into site-packages.
if ! python -c "import sgmllib" >/dev/null 2>&1; then
    echo "==> Applying sgmllib workaround for feedparser"
    SP="$(python -c 'import site; print(site.getsitepackages()[0])')"
    TMP="$(mktemp -d)"
    python -m pip download sgmllib3k --no-binary :all: --no-deps -d "$TMP" >/dev/null
    tar xzf "$TMP"/sgmllib3k-*.tar.gz -C "$TMP"
    cp "$TMP"/sgmllib3k-*/sgmllib.py "$SP/sgmllib.py"
    rm -rf "$TMP"
    echo "    installed sgmllib.py into $SP"
fi

# ---- Workaround #2: python-telegram-bot -> cryptography needs a working cffi
#      backend. If _cffi_backend is missing/broken, telegram import panics.
if ! python -c "import _cffi_backend" >/dev/null 2>&1; then
    echo "==> Installing cffi + cryptography for python-telegram-bot"
    python -m pip install --ignore-installed cffi cryptography
fi

echo "==> Verifying imports"
python -c "import feedparser, sgmllib, _cffi_backend; import ai_junkie_updates.main; print('imports OK')"

echo "==> Running offline tests"
python tests/test_pipeline_offline.py
python tests/test_agents_offline.py
python tests/test_preflight_offline.py

echo "==> Setup complete"
echo
echo "Next: check live-readiness (credentials + source reachability) with:"
echo "    python -m ai_junkie_updates.preflight"
