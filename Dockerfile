### Docker image for the RoboCoin dataset tooling (Python + uv + ffmpeg)
# syntax=docker/dockerfile:1.7

FROM ubuntu:24.04 AS runtime

ARG DEBIAN_FRONTEND=noninteractive

ENV TZ=UTC \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/robocoin/.venv \
    UV_CACHE_DIR=/opt/robocoin/.uv-cache \
    PATH="/opt/robocoin/.venv/bin:/root/.local/bin:${PATH}" \
    PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple" \
    UV_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"

RUN sed -i 's/archive.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list \
    && sed -i 's/security.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip python3-dev \
        build-essential pkg-config git curl ca-certificates \
        ffmpeg libgl1 libglib2.0-0 libsm6 libxrender1 libxext6 libglfw3 \
    && rm -rf /var/lib/apt/lists/*

# Install uv (Astral) for dependency management
# Attempt to install uv via pip, which should use the configured Chinese mirror.
# If this fails, consider alternative methods or a specific Chinese mirror for uv's install script.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

WORKDIR /opt/robocoin

# Copy the full repository (including the freshly generated requirements snapshot).
# NOTE: The Python environment inside the image is defined by `requirements-current.txt`
#       which is produced by `produceDockerImage.sh` from your currently active venv.
#       Always rerun that script to refresh the snapshot before building/exporting.
COPY . .

# Create virtualenv and install the exact package set captured on the host.
RUN uv venv --python python3 \
    && uv pip install --requirement requirements-current.txt \
    && uv pip install -e third_parties/robocoin-lerobot \
    && uv pip install -e .

# Default to an interactive shell so that users can run the CLI/tools directly
CMD ["bash"]
