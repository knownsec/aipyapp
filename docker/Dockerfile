FROM ghcr.io/astral-sh/uv:alpine

RUN apk update
RUN apk add --no-cache ttyd build-base gtk+3.0-dev

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

ADD . /app
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

EXPOSE 80

ENTRYPOINT ["/app/entrypoint.sh"]
