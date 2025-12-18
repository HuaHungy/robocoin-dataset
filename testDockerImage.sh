#!/usr/bin/env bash
# Docker Image Reproducibility Verification Script
# Features:
#   1. Load Docker image from .tar.gz file
#   2. Compare dependency lists between local environment and Docker image
#   3. Verify all critical dependencies can be imported successfully
#   4. Clean up all generated files and images after testing
# Usage:
#   ./testDockerImage.sh <IMAGE_FILE>
# Example:
#   ./testDockerImage.sh /home/rogerspyke/projects/robocoin-dataset.tar.gz

set -euo pipefail

# ==================== Global Variables Configuration ====================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPENDENCY_DIFF_FOUND=false

# Check if image file parameter is provided
if [[ $# -lt 1 ]]; then
    echo "Error: Please provide Docker image file path"
    echo "Usage: $0 <IMAGE_FILE>"
    echo "Example: $0 /path/to/robocoin-dataset.tar.gz"
    exit 1
fi

IMAGE_FILE="$1"
IMAGE_TAG=""  # Will be obtained after loading image
LOADED_IMAGE_ID=""  # Loaded image ID
ORIGINAL_REQ_FILE="${SCRIPT_DIR}/original-requirements.txt"
DOCKER_REQ_FILE="${SCRIPT_DIR}/docker-requirements.txt"
IMPORT_TEST_SCRIPT="${SCRIPT_DIR}/test_imports.py"
TEST_RESULTS_FILE="${SCRIPT_DIR}/import_test_results.txt"

# Color output configuration
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ==================== Utility Functions ====================

# Print info log
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Print success log
log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

# Print warning log
log_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

# Print error log and exit
log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
    exit 1
}

# Print separator line
print_separator() {
    echo "============================================================"
}

# ==================== Step 0: Pre-flight Checks ====================

check_prerequisites() {
    print_separator
    log_info "Step 0: Pre-flight checks"
    print_separator

    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
    fi
    log_success "Docker is installed"

    # Check if image file exists
    if [[ ! -f "${IMAGE_FILE}" ]]; then
        log_error "Image file '${IMAGE_FILE}' does not exist"
    fi
    log_success "Image file '${IMAGE_FILE}' found"

    # Check file extension
    if [[ ! "${IMAGE_FILE}" =~ \.(tar\.gz|tgz)$ ]]; then
        log_warning "File extension is not .tar.gz or .tgz, will try to load as compressed image"
    fi

    # Check if uv is installed
    if ! command -v uv &> /dev/null; then
        log_error "uv is not installed"
    fi
    log_success "uv is installed"

    # Check if virtual environment exists
    if [[ ! -d "${SCRIPT_DIR}/.venv" ]]; then
        log_warning "Virtual environment .venv does not exist"
        log_warning "Will skip virtual environment activation"
    else
        log_success "Virtual environment .venv found"
    fi

    echo ""
}

# ==================== Step 0.5: Load Docker Image ====================

load_docker_image() {
    print_separator
    log_info "Step 0.5: Load Docker image"
    print_separator

    log_info "Loading image from file: ${IMAGE_FILE}"

    # Load image and capture output
    local load_output=$(docker load -i "${IMAGE_FILE}" 2>&1)

    if [[ $? -ne 0 ]]; then
        log_error "Failed to load image"
        echo "$load_output"
        exit 1
    fi

    log_success "Image loaded successfully"
    echo "$load_output"

    # Extract image tag or ID from output
    # Output format is usually: "Loaded image: repository:tag" or "Loaded image ID: sha256:..."
    if echo "$load_output" | grep -q "Loaded image:"; then
        IMAGE_TAG=$(echo "$load_output" | grep "Loaded image:" | sed 's/Loaded image: //' | head -n 1)
        LOADED_IMAGE_ID=$(docker images --no-trunc --format "{{.ID}}" "${IMAGE_TAG}" | head -n 1)
    elif echo "$load_output" | grep -q "Loaded image ID:"; then
        LOADED_IMAGE_ID=$(echo "$load_output" | grep "Loaded image ID:" | sed 's/Loaded image ID: //' | sed 's/sha256://' | head -n 1)
        IMAGE_TAG="${LOADED_IMAGE_ID}"
    else
        log_error "Failed to extract image info from load output"
        exit 1
    fi

    log_success "Image tag/ID: ${IMAGE_TAG}"

    if [[ -n "${LOADED_IMAGE_ID}" ]]; then
        log_info "Full image ID: ${LOADED_IMAGE_ID}"
    fi

    echo ""
}

# ==================== Step 1: Export Local Dependencies ====================

export_local_dependencies() {
    print_separator
    log_info "Step 1: Export local dependencies"
    print_separator

    # Try to activate virtual environment (if exists)
    if [[ -d "${SCRIPT_DIR}/.venv" ]]; then
        log_info "Activating virtual environment"
        source "${SCRIPT_DIR}/.venv/bin/activate" || log_warning "Failed to activate virtual environment"
    fi

    # Export dependencies list
    log_info "Exporting local dependencies to ${ORIGINAL_REQ_FILE}"
    uv pip list --format=freeze > "${ORIGINAL_REQ_FILE}" || log_error "Failed to export local dependencies"

    local dep_count=$(wc -l < "${ORIGINAL_REQ_FILE}")
    log_success "Successfully exported ${dep_count} packages"

    echo ""
}

# ==================== Step 2: Export Docker Image Dependencies ====================

export_docker_dependencies() {
    print_separator
    log_info "Step 2: Export Docker image dependencies"
    print_separator

    log_info "Exporting dependencies from image '${IMAGE_TAG}' to ${DOCKER_REQ_FILE}"
    docker run --rm "${IMAGE_TAG}" uv pip list --format=freeze > "${DOCKER_REQ_FILE}" || log_error "Failed to export Docker dependencies"

    local dep_count=$(wc -l < "${DOCKER_REQ_FILE}")
    log_success "Successfully exported ${dep_count} packages"

    echo ""
}

# ==================== Step 3: Compare Dependency Lists ====================

compare_dependencies() {
    print_separator
    log_info "Step 3: Compare dependency lists"
    print_separator

    log_info "Comparing ${ORIGINAL_REQ_FILE} and ${DOCKER_REQ_FILE}"

    # Sort both files before comparison
    local sorted_original=$(mktemp)
    local sorted_docker=$(mktemp)
    sort "${ORIGINAL_REQ_FILE}" > "${sorted_original}"
    sort "${DOCKER_REQ_FILE}" > "${sorted_docker}"

    # Check if files are identical
    if diff -q "${sorted_original}" "${sorted_docker}" > /dev/null; then
        log_success "Dependency lists are identical"
        rm -f "${sorted_original}" "${sorted_docker}"
    else
        echo -e "${RED}[FAIL]${NC} Dependency lists differ"
        echo ""
        echo "========== Difference Details =========="

        # Create temporary files for package names only (without versions)
        local original_packages=$(mktemp)
        local docker_packages=$(mktemp)

        # Extract package names and create maps for version lookup
        declare -A original_versions
        declare -A docker_versions

        while IFS= read -r line; do
            if [[ -n "$line" ]]; then
                local pkg_name=$(echo "$line" | cut -d'=' -f1)
                local pkg_version=$(echo "$line" | sed 's/^[^=]*==//')
                echo "$pkg_name" >> "${original_packages}"
                original_versions["$pkg_name"]="$pkg_version"
            fi
        done < "${sorted_original}"

        while IFS= read -r line; do
            if [[ -n "$line" ]]; then
                local pkg_name=$(echo "$line" | cut -d'=' -f1)
                local pkg_version=$(echo "$line" | sed 's/^[^=]*==//')
                echo "$pkg_name" >> "${docker_packages}"
                docker_versions["$pkg_name"]="$pkg_version"
            fi
        done < "${sorted_docker}"

        # Sort package name files
        sort "${original_packages}" > "${original_packages}.sorted"
        sort "${docker_packages}" > "${docker_packages}.sorted"

        local has_differences=false

        # Find packages only in original (MISSING in Docker)
        while IFS= read -r pkg_name; do
            if [[ -n "$pkg_name" ]]; then
                if [[ -z "${docker_versions[$pkg_name]:-}" ]]; then
                    echo -e "${RED}[MISSING]${NC} ${pkg_name}==${original_versions[$pkg_name]}"
                    has_differences=true
                fi
            fi
        done < "${original_packages}.sorted"

        # Find packages only in Docker (EXTRA in Docker)
        while IFS= read -r pkg_name; do
            if [[ -n "$pkg_name" ]]; then
                if [[ -z "${original_versions[$pkg_name]:-}" ]]; then
                    echo -e "${YELLOW}[EXTRA]${NC} ${pkg_name}==${docker_versions[$pkg_name]}"
                    has_differences=true
                fi
            fi
        done < "${docker_packages}.sorted"

        # Find packages with different versions (DIFF_VER)
        while IFS= read -r pkg_name; do
            if [[ -n "$pkg_name" ]]; then
                local orig_ver="${original_versions[$pkg_name]:-}"
                local docker_ver="${docker_versions[$pkg_name]:-}"
                if [[ -n "$orig_ver" && -n "$docker_ver" && "$orig_ver" != "$docker_ver" ]]; then
                    echo -e "${YELLOW}[DIFF_VER]${NC} ${pkg_name}: local==${orig_ver}, docker==${docker_ver}"
                    has_differences=true
                fi
            fi
        done < "${original_packages}.sorted"

        # Clean up temporary files
        rm -f "${sorted_original}" "${sorted_docker}" \
              "${original_packages}" "${original_packages}.sorted" \
              "${docker_packages}" "${docker_packages}.sorted"

        echo "=================================================="
        DEPENDENCY_DIFF_FOUND=true
    fi

    echo ""
}

# ==================== Step 4: Generate Import Test Script ====================

# Package name to import name mapping table
declare -A PACKAGE_IMPORT_MAP=(
    ["opencv-python"]="cv2"
    ["opencv-python-headless"]="cv2"
    ["pillow"]="PIL"
    ["pyyaml"]="yaml"
    ["scikit-learn"]="sklearn"
    ["scikit-image"]="skimage"
    ["beautifulsoup4"]="bs4"
    ["python-dateutil"]="dateutil"
    ["protobuf"]="google.protobuf"
    ["attrs"]="attr"
    ["json-lines"]="jsonlines"
    ["numpy-quaternion"]="quaternion"
    ["absl-py"]="absl"
    ["fonttools"]="fontTools"
    ["gitpython"]="git"
    ["pyopengl"]="OpenGL"
    ["pyserial"]="serial"
    ["python-xlib"]="Xlib"
    ["pywavelets"]="pywt"
    ["pyyaml-include"]="yamlinclude"
    ["robocoin"]="robocoin"
    ["ruamel-yaml"]="ruamel.yaml"
    ["ruamel-yaml-clib"]="ruamel.yaml.clib"
    ["sphinxcontrib-applehelp"]="sphinxcontrib.applehelp"
    ["sphinxcontrib-devhelp"]="sphinxcontrib.devhelp"
    ["sphinxcontrib-htmlhelp"]="sphinxcontrib.htmlhelp"
    ["sphinxcontrib-jsmath"]="sphinxcontrib.jsmath"
    ["sphinxcontrib-qthelp"]="sphinxcontrib.qthelp"
    ["sphinxcontrib-serializinghtml"]="sphinxcontrib.serializinghtml"
    ["typer-slim"]="typer"
    ["websocket-client"]="websocket"
)

# Some packages ship data/libraries but no importable modules.
declare -A SKIP_IMPORT_PACKAGES=(
    ["nvidia-cublas-cu12"]=1
    ["nvidia-cuda-cupti-cu12"]=1
    ["nvidia-cuda-nvrtc-cu12"]=1
    ["nvidia-cuda-runtime-cu12"]=1
    ["nvidia-cudnn-cu12"]=1
    ["nvidia-cufft-cu12"]=1
    ["nvidia-cufile-cu12"]=1
    ["nvidia-curand-cu12"]=1
    ["nvidia-cusolver-cu12"]=1
    ["nvidia-cusparse-cu12"]=1
    ["nvidia-cusparselt-cu12"]=1
    ["nvidia-nccl-cu12"]=1
    ["nvidia-nvjitlink-cu12"]=1
    ["nvidia-nvtx-cu12"]=1
)

# Extract import name from package name
get_import_name() {
    local package_name="$1"

    # Remove version number, keep only package name
    package_name=$(echo "$package_name" | sed 's/==.*//')

    # Check if in mapping table
    if [[ -v PACKAGE_IMPORT_MAP["$package_name"] ]]; then
        echo "${PACKAGE_IMPORT_MAP[$package_name]}"
        return
    fi

    # Convert package name to import name (replace - with _)
    local import_name=$(echo "$package_name" | sed 's/-/_/g')

    # Special handling: take only the first part (for packages with .)
    import_name=$(echo "$import_name" | cut -d'.' -f1)

    echo "$import_name"
}

generate_import_test_script() {
    print_separator
    log_info "Step 4: Generate import test script"
    print_separator

    log_info "Extracting package names from ${ORIGINAL_REQ_FILE}"

    # Generate Python test script
    cat > "${IMPORT_TEST_SCRIPT}" << 'PYTHON_SCRIPT_EOF'
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Import test script for Docker image
"""

import sys
import importlib

def test_import(module_name):
    """Test single module import"""
    try:
        importlib.import_module(module_name)
        print(f"[OK] {module_name} OK")
        return True
    except ImportError as e:
        print(f"[FAIL] {module_name} FAILED: {e}")
        return False
    except Exception as e:
        print(f"[WARN] {module_name} ERROR: {e}")
        return False

def main():
    """Main test function"""
    # Module list to test (will be replaced by script)
    modules_to_test = [
PYTHON_SCRIPT_EOF

    # Add modules to test
    local module_count=0
    while IFS= read -r line; do
        # Skip empty lines and comments
        [[ -z "$line" || "$line" =~ ^# ]] && continue

        # Extract package name
        local package_name=$(echo "$line" | cut -d'=' -f1)

        # Skip packages that do not provide importable modules
        if [[ -v SKIP_IMPORT_PACKAGES["$package_name"] ]]; then
            continue
        fi

        # Get import name
        local import_name=$(get_import_name "$package_name")

        # Add to test script
        echo "        \"${import_name}\"," >> "${IMPORT_TEST_SCRIPT}"
        # Use addition instead of post-increment to avoid non-zero exit status under `set -e`
        ((module_count+=1))
    done < "${ORIGINAL_REQ_FILE}"

    # Complete Python script
    cat >> "${IMPORT_TEST_SCRIPT}" << 'PYTHON_SCRIPT_EOF'
    ]

    print("=" * 60)
    print("Starting import tests")
    print("=" * 60)
    print()

    success_count = 0
    failed_modules = []

    for module in modules_to_test:
        if test_import(module):
            success_count += 1
        else:
            failed_modules.append(module)

    print()
    print("=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    print(f"Total tests: {len(modules_to_test)} modules")
    print(f"Success: {success_count}")
    print(f"Failed: {len(failed_modules)}")

    if failed_modules:
        print()
        print("Failed modules:")
        for module in failed_modules:
            print(f"  - {module}")
        sys.exit(1)
    else:
        print()
        print("[SUCCESS] All modules imported successfully!")
        sys.exit(0)

if __name__ == "__main__":
    main()
PYTHON_SCRIPT_EOF

    chmod +x "${IMPORT_TEST_SCRIPT}"
    log_success "Test script generated with ${module_count} modules"

    echo ""
}

# ==================== Step 5: Execute Import Tests in Docker Container ====================

execute_import_tests() {
    print_separator
    log_info "Step 5: Execute import tests in Docker container"
    print_separator

    log_info "Running test script in image '${IMAGE_TAG}'"

    # Copy test script to container and execute
    if docker run --rm -v "${IMPORT_TEST_SCRIPT}:/tmp/test_imports.py:ro" \
        "${IMAGE_TAG}" python3 /tmp/test_imports.py | tee "${TEST_RESULTS_FILE}"; then
        log_success "All import tests passed"
    else
        echo -e "${RED}[FAIL]${NC} Some import tests failed"
        exit 1
    fi

    echo ""
}

# ==================== Step 6: Clean Up All Resources ====================

cleanup_all_resources() {
    print_separator
    log_info "Step 6: Clean up all resources"
    print_separator

    # Clean up all generated files
    log_info "Cleaning up all generated files"

    local files_to_remove=(
        "${ORIGINAL_REQ_FILE}"
        "${DOCKER_REQ_FILE}"
        "${IMPORT_TEST_SCRIPT}"
        "${TEST_RESULTS_FILE}"
    )

    for file in "${files_to_remove[@]}"; do
        if [[ -f "$file" ]]; then
            rm -f "$file"
            log_success "Removed file: $file"
        fi
    done

    # Remove loaded Docker image
    if [[ -n "${LOADED_IMAGE_ID}" ]] || [[ -n "${IMAGE_TAG}" ]]; then
        log_info "Removing loaded Docker image"

        local image_to_remove="${LOADED_IMAGE_ID:-${IMAGE_TAG}}"

        if docker image inspect "${image_to_remove}" &> /dev/null; then
            if docker rmi "${image_to_remove}" &> /dev/null; then
                log_success "Removed image: ${image_to_remove}"
            else
                log_warning "Failed to remove image (may be in use)"
            fi
        else
            log_info "Image does not exist, no need to remove"
        fi
    fi

    echo ""
}

# ==================== Cleanup Handler (Ensure Resources Are Cleaned Up) ====================

cleanup_handler() {
    local exit_code=$?

    # If not normal exit, show cleanup message
    if [[ $exit_code -ne 0 ]]; then
        echo ""
        log_warning "Abnormal exit detected, starting cleanup..."
    fi

    # Execute cleanup
    cleanup_all_resources

    exit $exit_code
}

# Register cleanup handler on exit
trap cleanup_handler EXIT

# ==================== Main Workflow ====================

main() {
    echo ""
    print_separator
    log_info "Docker Image Reproducibility Verification"
    log_info "Image file: ${IMAGE_FILE}"
    print_separator
    echo ""

    # Execute each step
    check_prerequisites
    load_docker_image
    export_local_dependencies
    export_docker_dependencies
    compare_dependencies
    generate_import_test_script
    execute_import_tests

    if [[ "${DEPENDENCY_DIFF_FOUND}" == "true" ]]; then
        print_separator
        log_error "Dependency differences detected, see details above."
    fi

    # Final conclusion
    print_separator
    log_success "[SUCCESS] Image verification passed!"
    log_success "Docker image '${IMAGE_TAG}' is fully reproducible"
    print_separator
    echo ""

    # Note: Cleanup will be executed automatically by trap
}

# Execute main workflow
main
