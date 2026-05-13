#!/bin/bash

run_privileged() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    else
        sudo "$@"
    fi
}

SERVICE_NAME="opencapy"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "Stopping and disabling service: ${SERVICE_NAME}"
run_privileged systemctl stop "${SERVICE_NAME}.service"
run_privileged systemctl disable "${SERVICE_NAME}.service"

echo "Removing service file: ${SERVICE_FILE}"
run_privileged rm -f "${SERVICE_FILE}"

run_privileged systemctl daemon-reload
run_privileged systemctl reset-failed

echo "Service uninstalled."