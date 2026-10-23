#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="Nexus Requests"
INSTALL_DIR="/opt/nexus-requests"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() {
    printf '[Nexus Requests] %s\n' "$*"
}

fail() {
    printf '[Nexus Requests] ERROR: %s\n' "$*" >&2
    exit 1
}

check_prerequisites() {
    [[ $EUID -eq 0 ]] ||
        fail "Run this installer as root."

    [[ -f /etc/os-release ]] ||
        fail "Cannot identify operating system."

    . /etc/os-release

    [[ "$ID" == "debian" ]] ||
        fail "Debian is required."

    [[ "$VERSION_ID" == "13" ]] ||
        fail "Debian 13 is required."

    for cmd in apt-get systemctl; do
        command -v "$cmd" >/dev/null 2>&1 ||
            fail "Missing required system command: $cmd"
    done

    [[ ! -e "$INSTALL_DIR" ]] ||
        fail "$INSTALL_DIR already exists. Refusing to overwrite."

    log "Prerequisite checks passed."
}

REPO="lakeryan443-ui/nexus-requests"

get_release_tag() {
    local response tag

    response="$(curl -fsSL \
        -H "Accept: application/vnd.github+json" \
        "https://api.github.com/repos/$REPO/releases/latest")" ||
        fail "Could not retrieve the latest GitHub release."

    tag="$(printf '%s' "$response" | python3 -c \
        'import json,sys; print(json.load(sys.stdin).get("tag_name", ""))')" ||
        fail "Invalid GitHub release response."

    [[ "$tag" =~ ^v[0-9]+\\.[0-9]+\\.[0-9]+$ ]] ||
        fail "No valid stable release tag was found."

    printf '%s\\n' "$tag"
}

download_release() {
    local tag="$1"
    local archive_url
    local archive_file
    local staging_dir

    [[ "$tag" =~ ^v[0-9]+\\.[0-9]+\\.[0-9]+$ ]] ||
        fail "Invalid release tag."

    [[ ! -e "$INSTALL_DIR" ]] ||
        fail "$INSTALL_DIR already exists."

    archive_url="https://github.com/$REPO/archive/refs/tags/$tag.tar.gz"

    staging_dir="$(mktemp -d)"
    archive_file="$staging_dir/release.tar.gz"

    log "Downloading Nexus Requests $tag..."

    if ! curl -fsSL --retry 3 \
        "$archive_url" -o "$archive_file"; then
        rm -rf -- "$staging_dir"
        fail "Release download failed."
    fi

    mkdir -p "$staging_dir/extracted"

    if ! tar -xzf "$archive_file" \
        --strip-components=1 \
        -C "$staging_dir/extracted"; then
        rm -rf -- "$staging_dir"
        fail "Release extraction failed."
    fi

    if [[ ! -f "$staging_dir/extracted/bot.py" ||
          ! -f "$staging_dir/extracted/requirements.txt" ||
          ! -f "$staging_dir/extracted/webgui/app.py" ]]; then
        rm -rf -- "$staging_dir"
        fail "Release archive is missing required files."
    fi

    mv "$staging_dir/extracted" "$INSTALL_DIR"
    rm -rf -- "$staging_dir"

    log "Nexus Requests $tag downloaded successfully."
}

install_system_packages() {
    log "Installing Debian system dependencies..."

    apt-get update ||
        fail "Could not update Debian package lists."

    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        ca-certificates \
        curl \
        tar \
        python3 \
        python3-venv \
        python3-pip ||
        fail "Could not install required Debian packages."

    log "Debian system dependencies installed."
}

install_dependencies() {
    log "Creating shared Python environment..."

    python3 -m venv "$INSTALL_DIR/venv" ||
        fail "Could not create Python virtual environment."

    log "Installing Python dependencies..."

    "$INSTALL_DIR/venv/bin/python" -m pip install \
        --disable-pip-version-check \
        -r "$INSTALL_DIR/requirements.txt" ||
        fail "Python dependency installation failed."

    log "Python dependencies installed successfully."
}

install_services() {
    log "Installing systemd services..."

    cat > /etc/systemd/system/nexus-requests-bot.service <<EOF
[Unit]
Description=Nexus Requests Discord Bot
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/bot.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    cat > /etc/systemd/system/nexus-requests-webgui.service <<EOF
[Unit]
Description=Nexus Requests WebGUI
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR/webgui
ExecStart=$INSTALL_DIR/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8081
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    cat > /etc/systemd/system/nexus-requests-scheduler.service <<EOF
[Unit]
Description=Nexus Requests Download Scheduler
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR/webgui
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/webgui/scheduler_worker.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload ||
        fail "Could not reload systemd."

    log "Systemd services installed."
}

main() {
    log "Preparing $APP_NAME installation"

    check_prerequisites
    install_system_packages

    local tag
    tag="${NEXUS_VERSION:-}"

    if [[ -z "$tag" ]]; then
        tag="$(get_release_tag)"
    fi

    download_release "$tag"
    install_dependencies
    install_services

    systemctl enable --now nexus-requests-webgui.service ||
        fail "Could not start Nexus Requests WebGUI."

    systemctl enable --now nexus-requests-scheduler.service ||
        fail "Could not start Nexus Requests scheduler."

    log "Nexus Requests $tag installed successfully."
    log "Open http://SERVER-IP:8081 to complete setup."
    log "Discord bot and scheduler remain inactive until configured."
}

main "$@"
