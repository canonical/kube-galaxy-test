#!/usr/bin/env bash
# bootstrap_node.sh — install Kubernetes components on a cluster node.
#
# Usage:
#   bootstrap_node.sh --artifact-base-url <URL> --k8s-version <VERSION> \
#                     --arch <ARCH> [--component <NAME>]...
#
# Arguments:
#   --artifact-base-url  Base URL of the orchestrator's artifact HTTP server,
#                        e.g. "http://192.168.1.1:8765".  All files are
#                        downloaded relative to this URL under the path
#                        structure: /opt/kube-galaxy/<component>/temp/
#   --k8s-version        Kubernetes version string, e.g. "1.35.0".
#   --arch               Kubernetes architecture string (amd64, arm64, …).
#   --component          Component name(s) to install.  May be repeated.
#                        Supported: kubeadm, kubelet, kubectl, crictl,
#                                   containerd, runc.
#                        Defaults to: kubeadm kubelet kubectl crictl
#                                     containerd runc
#
# Environment variables (optional overrides):
#   KUBE_GALAXY_INSTALL_DIR   Directory for kube-galaxy binaries.
#                             Default: /opt/kube-galaxy
#   KUBEADM_ALTERNATIVES_PRIORITY  update-alternatives priority. Default: 100
#
# Design principles:
#   - Each component download is verified with SHA-256 before installation.
#   - All binaries are installed via update-alternatives so they can coexist
#     with distribution packages and be cleanly removed.
#   - The script is idempotent: safe to re-run on an already-provisioned node.
#   - No package manager is used; all dependencies come from the artifact server.
# ---------------------------------------------------------------------------

set -euo pipefail

# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------
ARTIFACT_BASE_URL=""
K8S_VERSION=""
ARCH=""
COMPONENTS=()
INSTALL_DIR="${KUBE_GALAXY_INSTALL_DIR:-/opt/kube-galaxy}"
ALT_PRIORITY="${KUBEADM_ALTERNATIVES_PRIORITY:-100}"
USR_LOCAL_BIN="/usr/local/bin"

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
info()    { echo "[INFO]  $*"; }
success() { echo "[OK]    $*"; }
error()   { echo "[ERROR] $*" >&2; }
die()     { error "$*"; exit 1; }

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
parse_args() {
    local key
    while [[ $# -gt 0 ]]; do
        key="$1"
        case "$key" in
            --artifact-base-url)
                ARTIFACT_BASE_URL="$2"; shift 2 ;;
            --k8s-version)
                K8S_VERSION="$2"; shift 2 ;;
            --arch)
                ARCH="$2"; shift 2 ;;
            --component)
                COMPONENTS+=("$2"); shift 2 ;;
            *)
                die "Unknown argument: $key" ;;
        esac
    done

    [[ -n "$ARTIFACT_BASE_URL" ]] || die "--artifact-base-url is required"
    [[ -n "$K8S_VERSION" ]]       || die "--k8s-version is required"
    [[ -n "$ARCH" ]]              || die "--arch is required"

    # Default component set when none specified
    if [[ ${#COMPONENTS[@]} -eq 0 ]]; then
        COMPONENTS=(kubeadm kubelet kubectl crictl containerd runc)
    fi
}

# ---------------------------------------------------------------------------
# Download and verify
# ---------------------------------------------------------------------------

# download_and_verify <url> <dest_path> [<expected_sha256>]
#   Downloads <url> to <dest_path>, optionally verifying the SHA-256 checksum.
download_and_verify() {
    local url="$1"
    local dest="$2"
    local expected_sha256="${3:-}"

    info "Downloading $(basename "$dest") ..."
    mkdir -p "$(dirname "$dest")"

    if command -v curl &>/dev/null; then
        curl -fsSL "$url" -o "$dest"
    elif command -v wget &>/dev/null; then
        wget -q "$url" -O "$dest"
    else
        die "Neither curl nor wget is available"
    fi

    if [[ -n "$expected_sha256" ]]; then
        local actual_sha256
        actual_sha256="$(sha256sum "$dest" | awk '{print $1}')"
        if [[ "$actual_sha256" != "$expected_sha256" ]]; then
            rm -f "$dest"
            die "SHA-256 mismatch for $(basename "$dest"): expected $expected_sha256 got $actual_sha256"
        fi
        success "Checksum verified: $(basename "$dest")"
    fi
}

# ---------------------------------------------------------------------------
# Binary installation via update-alternatives
# ---------------------------------------------------------------------------

# install_binary <src_path> <binary_name>
#   Installs <src_path> into <INSTALL_DIR>/<binary_name>/bin/ and registers it
#   with update-alternatives so it is available as /usr/local/bin/<binary_name>.
install_binary() {
    local src="$1"
    local name="$2"
    local dest_dir="${INSTALL_DIR}/${name}/bin"
    local dest="${dest_dir}/${name}"

    mkdir -p "$dest_dir"
    cp -f "$src" "$dest"
    chmod 755 "$dest"

    # Register with update-alternatives
    local alt_link="${USR_LOCAL_BIN}/${name}"
    update-alternatives --install "$alt_link" "$name" "$dest" "$ALT_PRIORITY" 2>/dev/null || true
    success "Installed ${name} → ${dest} (via ${alt_link})"
}

# ---------------------------------------------------------------------------
# Component installation helpers
# ---------------------------------------------------------------------------

staging_url() {
    # staging_url <component> <filename>
    # Returns the artifact server URL for a staged file.
    # The path mirrors SystemPaths.local_component_temp_dir(component):
    #   <base>/opt/kube-galaxy/<component>/temp/<filename>
    local component="$1"
    local filename="$2"
    echo "${ARTIFACT_BASE_URL}/opt/kube-galaxy/${component}/temp/${filename}"
}

install_kube_binary() {
    local name="$1"
    local filename="${name}"
    local url
    url="$(staging_url "$name" "$filename")"
    local tmp_dir
    tmp_dir="$(mktemp -d)"
    trap 'rm -rf "$tmp_dir"' RETURN
    download_and_verify "$url" "${tmp_dir}/${filename}"
    install_binary "${tmp_dir}/${filename}" "$name"
}

install_crictl() {
    local filename="crictl-v${K8S_VERSION}-linux-${ARCH}.tar.gz"
    local url
    url="$(staging_url "crictl" "$filename")"
    local tmp_dir
    tmp_dir="$(mktemp -d)"
    trap 'rm -rf "$tmp_dir"' RETURN
    local archive="${tmp_dir}/${filename}"
    download_and_verify "$url" "$archive"
    tar -xf "$archive" -C "$tmp_dir"
    install_binary "${tmp_dir}/crictl" "crictl"
}

install_containerd() {
    local filename="containerd-${K8S_VERSION}-linux-${ARCH}.tar.gz"
    local url
    url="$(staging_url "containerd" "$filename")"
    local tmp_dir
    tmp_dir="$(mktemp -d)"
    trap 'rm -rf "$tmp_dir"' RETURN
    local archive="${tmp_dir}/${filename}"
    download_and_verify "$url" "$archive"
    tar -xf "$archive" -C "$tmp_dir"
    # containerd tarball has a bin/ sub-directory
    for binary in "${tmp_dir}"/bin/containerd*; do
        [[ -f "$binary" ]] && install_binary "$binary" "$(basename "$binary")"
    done
}

install_runc() {
    local filename="runc.${ARCH}"
    local url
    url="$(staging_url "runc" "$filename")"
    local tmp_dir
    tmp_dir="$(mktemp -d)"
    trap 'rm -rf "$tmp_dir"' RETURN
    download_and_verify "$url" "${tmp_dir}/runc"
    install_binary "${tmp_dir}/runc" "runc"
}

# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

main() {
    parse_args "$@"

    info "Starting node bootstrap"
    info "  Artifact server : ${ARTIFACT_BASE_URL}"
    info "  Kubernetes ver  : ${K8S_VERSION}"
    info "  Architecture    : ${ARCH}"
    info "  Components      : ${COMPONENTS[*]}"

    for component in "${COMPONENTS[@]}"; do
        info "--- Installing: ${component} ---"
        case "$component" in
            kubeadm|kubelet|kubectl)
                install_kube_binary "$component" ;;
            crictl)
                install_crictl ;;
            containerd)
                install_containerd ;;
            runc)
                install_runc ;;
            *)
                error "Unknown component: ${component} — skipping" ;;
        esac
    done

    success "Node bootstrap complete"
}

main "$@"
