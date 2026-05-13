#!/bin/bash

run_privileged() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    else
        sudo "$@"
    fi
}

SERVICE_NAME="opencapy"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SERVICE_USER="${SUDO_USER:-$USER}"
SERVICE_HOME="$(getent passwd "${SERVICE_USER}" | cut -d: -f6)"

echo "Creating systemd service: ${SERVICE_NAME}"

run_privileged tee "${SERVICE_FILE}" >/dev/null <<EOF
[Unit]
Description=OpenCapy Agent
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${PROJECT_DIR}
Environment=PATH=${SERVICE_HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/bin/bash ${PROJECT_DIR}/start.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

run_privileged systemctl daemon-reload
run_privileged systemctl enable "${SERVICE_NAME}.service"
run_privileged systemctl restart "${SERVICE_NAME}.service"
run_privileged systemctl status "${SERVICE_NAME}.service" --no-pager

echo "Service installed and running."