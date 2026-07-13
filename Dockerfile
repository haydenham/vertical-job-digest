# Rolefeed / vja — production image (Phase 9.5b, D-060).
#
# One image, two run targets (D-031 "scheduler is a swappable trigger"):
#   • Cloud Run service: the default CMD below — `vja-api` serves the read API + the SPA same-origin.
#   • Cloud Run Job:     override the entrypoint to `/app/.venv/bin/vja-nightly` — no second build.
#
# The SPA is built in stage `web` (Debian/glibc — avoids the alpine/musl Rollup optional-binary
# break) and copied into the runtime image; FastAPI serves it from `VJA_FRONTEND_DIST` (9.5b), which
# is needed because the non-editable install moves the package out of the repo layout that
# `frontend_dist_dir()`'s default assumes.
#
# Local prod-parity smoke:
#   docker build -t rolefeed:smoke .
#   docker run --rm -p 8000:8000 rolefeed:smoke
#   curl -s localhost:8000/api/health   # {"status":"ok"}
#   curl -s localhost:8000/ ; curl -s localhost:8000/upload   # index.html (catch-all)

# ---- stage 1: build the SPA -------------------------------------------------
FROM node:24-bookworm-slim AS web
WORKDIR /web/frontend
# package*.json first so `npm ci` is cached until deps actually change.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build   # → /web/frontend/dist

# ---- stage 2: python runtime ------------------------------------------------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Dependencies layer (cached until pyproject/lock change). README.md is referenced by
# [project].readme so the wheel build needs it present.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project --no-editable

# The package itself — non-editable (immutable installed artifact, not a /app/src .pth link).
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

# Runtime data the wheel doesn't carry: alembic needs migrations/ + alembic.ini adjacent for the
# 9.5d `alembic upgrade`; nightly/import needs the vertical config + employer seed.
COPY alembic.ini ./
COPY migrations ./migrations
COPY config ./config
COPY data/seed ./data/seed

# The built SPA, served same-origin by FastAPI via the explicit dist path.
COPY --from=web /web/frontend/dist ./frontend/dist
ENV VJA_FRONTEND_DIST=/app/frontend/dist \
    VJA_ALEMBIC_INI=/app/alembic.ini
# The non-editable install moves vja into site-packages, so the code's repo-relative default for the
# vertical configs (`parents[2]`) misses; point it at the copied config dir (nightly Layer-2 reads it).
ENV VJA_VERTICALS_DIR=/app/config/verticals

# Cloud Run injects $PORT (default 8080); bind 0.0.0.0. Local dev still defaults 127.0.0.1:8000.
CMD ["/app/.venv/bin/vja-api", "--host", "0.0.0.0"]
