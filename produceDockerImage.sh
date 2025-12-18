#!/usr/bin/env bash
# Build and optionally export the RoboCoin dataset Docker image.
# Usage:
#   ./produceDockerImage.sh [image-tag] [build-context]          # only build
#   ./produceDockerImage.sh --export [image-tag] [output-file]   # build + export
# Example:
#   ./produceDockerImage.sh --export latest /home/rogerspyke/projects/robocoin-dataset.tar.gz

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER_WORKDIR="/opt/robocoin"
ENV_SNAPSHOT_FILE="requirements-current.txt"

# Always operate from the repository root so that `pyproject.toml` and
# `uv.lock` are resolved consistently regardless of where the script is run.
cd "${SCRIPT_DIR}"

# Default values
IMAGE_TAG="robocoin-dataset:latest"
BUILD_CONTEXT="${SCRIPT_DIR}"
EXPORT=false
OUTPUT_FILE="robocoin-dataset.tar.gz"

# Retry configuration
MAX_RETRIES=1000
RETRY_DELAY=30

# Parse arguments
if [[ $# -gt 0 ]] && [[ "$1" == "--export" ]]; then
    EXPORT=true
    shift
    IMAGE_TAG="${1:-robocoin-dataset:latest}"
    OUTPUT_FILE="${2:-robocoin-dataset.tar.gz}"
else
    IMAGE_TAG="${1:-robocoin-dataset:latest}"
    BUILD_CONTEXT="${2:-${SCRIPT_DIR}}"
fi

# Retry function
retry_command() {
    local cmd="$1"
    local max_retries="$2"
    local delay="$3"
    local attempt=1

    while [[ $attempt -le $max_retries ]]; do
        echo ">>>Attempt $attempt/$max_retries: $cmd"
        if eval "$cmd"; then
            echo "<SUCCESS> Command succeeded on attempt $attempt"
            return 0
        else
            echo "<FAILED> Command failed on attempt $attempt"
            if [[ $attempt -lt $max_retries ]]; then
                echo ">>>Waiting ${delay}s before retry..."
                sleep "$delay"
            fi
        fi
        ((attempt++))
    done

    echo "<ERROR> Command failed after $max_retries attempts"
    return 1
}

# Export the currently installed dependencies so Docker can recreate
# the exact same environment without re-resolving pyproject.toml.
snapshot_current_environment() {
    echo ">>>Capturing current environment into ${ENV_SNAPSHOT_FILE}..."

    local tmp_file
    tmp_file="$(mktemp)"

    if command -v uv &> /dev/null; then
        if ! uv pip freeze --exclude-editable > "${tmp_file}"; then
            echo "<ERROR> Failed to run 'uv pip freeze'"
            rm -f "${tmp_file}"
            return 1
        fi
    elif command -v python3 &> /dev/null; then
        if ! python3 -m pip freeze --exclude-editable > "${tmp_file}"; then
            echo "<ERROR> Failed to run 'python3 -m pip freeze'"
            rm -f "${tmp_file}"
            return 1
        fi
    else
        echo "<ERROR> Neither 'uv' nor 'python3' is available to snapshot dependencies"
        rm -f "${tmp_file}"
        return 1
    fi

    if ! command -v python3 &> /dev/null; then
        echo "<ERROR> python3 is required to rewrite ${ENV_SNAPSHOT_FILE}"
        rm -f "${tmp_file}"
        return 1
    fi

    # Replace host-specific absolute paths (file:///...) with the path that will
    # exist inside the container so local path dependencies continue to work.
    if ! python3 - "${tmp_file}" "${ENV_SNAPSHOT_FILE}" "${SCRIPT_DIR}" "${CONTAINER_WORKDIR}" <<'PY'
import pathlib
import sys

tmp_path, output_path, host_root, container_root = sys.argv[1:5]
host_uri = pathlib.Path(host_root).resolve().as_uri()
container_uri = pathlib.Path(container_root).resolve().as_uri()

with open(tmp_path, "r", encoding="utf-8") as src, open(output_path, "w", encoding="utf-8") as dst:
    for line in src:
        # Preserve comments and blank lines verbatim
        if line.strip().startswith("#") or not line.strip():
            dst.write(line)
            continue
        dst.write(line.replace(host_uri, container_uri))
PY
    then
        local rewrite_status=$?
        rm -f "${tmp_file}"
        echo "<ERROR> Failed to rewrite ${ENV_SNAPSHOT_FILE} with container paths"
        return "${rewrite_status}"
    fi

    rm -f "${tmp_file}"

    echo "<SUCCESS> Wrote ${ENV_SNAPSHOT_FILE} from current environment"
}

echo ">>>Snapshotting current Python environment..."
snapshot_current_environment

echo ">>>Building image '${IMAGE_TAG}' from context '${BUILD_CONTEXT}' (with retry mechanism)"
retry_command "docker build -t \"${IMAGE_TAG}\" \"${BUILD_CONTEXT}\"" "$MAX_RETRIES" "$RETRY_DELAY"
echo "<SUCCESS> Image '${IMAGE_TAG}' built successfully."

if [[ "$EXPORT" == true ]]; then
    echo ">>>Exporting image to '${OUTPUT_FILE}' (compressed with gzip)..."
    docker save "${IMAGE_TAG}" | gzip > "${OUTPUT_FILE}"
    echo "<SUCCESS>Image exported to '${OUTPUT_FILE}'"
    ls -lh "${OUTPUT_FILE}"
fi
