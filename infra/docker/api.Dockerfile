# Production image for API / worker / scheduler (same code, different command).
FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VERSION=2.3.2 \
    POETRY_VIRTUALENVS_CREATE=false \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Unicode font for Turkish PDF reports (see visionroute.config.fonts).
ENV VISIONROUTE_PDF_FONT_DIR=/usr/share/fonts/truetype/dejavu

FROM base AS build
RUN pip install "poetry==${POETRY_VERSION}"
WORKDIR /app
# README.md is the package readme declared in pyproject.toml (needed to install the project).
COPY pyproject.toml poetry.lock README.md ./
RUN poetry install --only main --no-root
COPY src ./src
COPY alembic.ini ./
RUN poetry install --only main

FROM base AS runtime
# Non-root runtime user (least privilege).
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app
COPY --from=build /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=build /usr/local/bin /usr/local/bin
COPY --from=build /app /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD curl -fsS http://localhost:8000/health/live || exit 1

# Default command runs the API; compose/ECS override for worker & scheduler.
# --proxy-headers: client IPs come from X-Forwarded-For, trusted only from
# FORWARDED_ALLOW_IPS (127.0.0.1 by default; ECS sets it because tasks are
# reachable only from the load balancer's security group).
# Keep-alive exceeds the ALB idle timeout (60 s) to avoid 502s on reused
# connections.
CMD ["uvicorn", "visionroute.api.main:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--timeout-keep-alive", "75"]
