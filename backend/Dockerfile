FROM python:3.13-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PLAYWRIGHT_BROWSERS_PATH=/ms-playwright PATH="/app/.venv/bin:$PATH"
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project \
 && playwright install --with-deps chromium \
 && apt-get install -y --no-install-recommends xvfb xauth \
 && rm -rf /var/lib/apt/lists/*

COPY app ./app

EXPOSE 8000
# Headed Chromium on a virtual display (Xvfb): looks less like a bot than headless, nothing opens on your machine.
CMD ["xvfb-run", "-a", "--server-args=-screen 0 1280x800x24", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
