#!/bin/sh
set -e

# Put caches and model downloads into a location outside /app so they are not
# overwritten by the host bind mount. This directory is configured in the
# Dockerfile and exposed as a named volume in docker-compose.yml.
CACHE_DIR="/var/lib/voiceagent/cache"
mkdir -p "$CACHE_DIR"
chown -R appuser:appuser /var/lib/voiceagent || true

export XDG_CACHE_HOME="$CACHE_DIR"
export HF_HOME="$CACHE_DIR"
export TRANSFORMERS_CACHE="$CACHE_DIR"

# Run the download step first so required model files (e.g., languages.json)
# are present before starting the agent. Continue even if the download step
# fails so container can still start for debugging; however, failures will be
# visible in the logs.
echo "Downloading model files into $CACHE_DIR (this may take a while)"
uv run src/agent.py download-files || echo "download-files failed; check logs"

# Exec the normal start command so signals are forwarded correctly.
exec uv run src/agent.py start
