# --- Base image ---
# Using the "slim" variant, not the full python image: it's ~150MB smaller,
# which speeds up deploys and reduces attack surface (fewer installed
# packages = fewer potential vulnerabilities to patch).
FROM python:3.12-slim

# Prevents Python from writing .pyc files and buffers stdout -- both matter
# in containers: .pyc files are pointless in an ephemeral container, and
# unbuffered stdout means your logs appear in `docker logs` immediately
# instead of being held in a buffer.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy and install requirements BEFORE copying the rest of the source code.
# This is a deliberate layer-caching optimization: Docker caches each layer,
# and this file only changes when dependencies change. If we copied all the
# source code first, every single code edit would invalidate the pip install
# layer too, forcing a full reinstall on every build -- this ordering means
# `docker build` after a code-only change reuses the cached dependency layer
# and finishes in seconds instead of minutes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the actual application code.
COPY app ./app

# Runs as a non-root user. Running containers as root is a common security
# misconfiguration -- if an attacker ever achieves code execution inside the
# container (e.g. via a dependency vulnerability), running as non-root
# limits what they can do within that container.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

# Production command: no --reload (that's dev-only, and it adds file-
# watching overhead you don't want in production). Render/most platforms
# override this via their own start command, but this is a valid default
# for `docker run` directly.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
