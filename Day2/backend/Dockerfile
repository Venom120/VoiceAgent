# syntax=docker/dockerfile:1

# Use the official UV Python base image with Python 3.13 on Debian Bookworm
# UV is a fast Python package manager that provides better performance than pip
# We use the slim variant to keep the image size smaller while still having essential tools
ARG PYTHON_VERSION=3.13
FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-bookworm-slim AS base

# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

# Create a non-privileged user that the app will run under.
# See https://docs.docker.com/develop/develop-images/dockerfile_best-practices/#user
ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/app" \
    --shell "/sbin/nologin" \
    --uid "${UID}" \
    appuser

# Install build dependencies required for Python packages with native extensions
# gcc: C compiler needed for building Python packages with C extensions
# python3-dev: Python development headers needed for compilation
# We clean up the apt cache after installation to keep the image size down
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    python3-dev \
  && rm -rf /var/lib/apt/lists/*

# Create a new directory for our application code
# And set it as the working directory
WORKDIR /app

# Copy just the dependency files first, for more efficient layer caching
COPY pyproject.toml uv.lock ./
RUN mkdir -p src

# Install Python dependencies using UV's lock file
# --locked ensures we use exact versions from uv.lock for reproducible builds
# This creates a virtual environment and installs all dependencies
# Ensure your uv.lock file is checked in for consistency across environments
RUN uv sync --locked

# Copy all remaining application files into the container
# This includes source code, configuration files, and dependency specifications
# (Excludes files specified in .dockerignore)
COPY . .

# Change ownership of all app files to the non-privileged user
# This ensures the application can read/write files as needed
RUN chown -R appuser:appuser /app

# Switch to the non-privileged user for all subsequent operations
# This improves security by not running as root
USER appuser

# Create a directory outside of /app to store downloaded ML models and cache.
# Storing model files under /var/lib/voiceagent/cache keeps them separate from
# the project bind mount (which overrides /app at runtime) and allows a named
# Docker volume to persist them across container restarts.
USER root
RUN mkdir -p /var/lib/voiceagent/cache && chown -R appuser:appuser /var/lib/voiceagent
USER appuser

# Copy an entrypoint script that will run the download step at container start
# (after bind mounts are applied) and then start the agent. Downloading at
# runtime ensures model files aren't hidden by the host bind mount of /app.
COPY --chown=appuser:appuser entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Allow mounting the project folder at runtime so local edits are
# reflected inside the container. Keep the virtualenv or installed
# files used by the runtime in a separate volume so they aren't
# lost/overwritten by a host bind mount.
VOLUME ["/app"]

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uv", "run", "src/agent.py", "start"]
