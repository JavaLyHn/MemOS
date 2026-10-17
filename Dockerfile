# MemOS Production Dockerfile
# Multi-stage build with optimizations

# Stage 1: Install dependencies
FROM python:3.11-slim AS builder

# PyPI 源。默认走国内镜像——直连 pypi.org 实测只有 27-80 kB/s，装一遍 130 个包
# 要半小时以上，numpy 一个 16.9 MB 的包就下了 20 分钟。
# 内网有私有源就用 --build-arg PIP_INDEX_URL=<内网地址> 覆盖。
ARG PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    build-essential \
    libffi-dev \
    python3-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY docker/requirements.txt .
RUN pip install --upgrade pip -i "$PIP_INDEX_URL" && \
    pip install --prefix=/install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt

# Stage 2: Runtime image
FROM python:3.11-slim

ARG PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 memos

WORKDIR /app

ENV HF_ENDPOINT=https://hf-mirror.com
ENV PYTHONPATH=/app/src
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY --from=builder /install /usr/local
COPY src/ ./src
COPY docker/ ./docker

# 装上本包自身。没有 dist-info 时 importlib.metadata.entry_points() 读不到
# [project.entry-points."memos.plugins"]，MEMOS_ENABLED_PLUGINS 里写了 dream /
# hallucination_guard 也不会有任何插件被加载（静默失效）。
# --no-deps：依赖已由上面的 requirements.txt 装好，这一步只为拿元数据。
# 运行时代码仍从 /app/src 加载（PYTHONPATH），所以热补丁挂载不受影响。
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir --no-deps -i "$PIP_INDEX_URL" . && rm -f pyproject.toml README.md

RUN chown -R memos:memos /app

USER memos

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "memos.api.server_api:app", "--host", "0.0.0.0", "--port", "8000"]
