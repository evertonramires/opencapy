#!/bin/bash

run_privileged() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    else
        sudo "$@"
    fi
}

install_package() {
    package_name="$1"

    if command -v apt-get >/dev/null 2>&1; then
        run_privileged apt-get update
        run_privileged apt-get install -y "$package_name"
        return
    fi

    if command -v dnf >/dev/null 2>&1; then
        run_privileged dnf install -y "$package_name"
        return
    fi

    if command -v yum >/dev/null 2>&1; then
        run_privileged yum install -y "$package_name"
        return
    fi

    if command -v pacman >/dev/null 2>&1; then
        run_privileged pacman -Sy --noconfirm "$package_name"
        return
    fi

    if command -v apk >/dev/null 2>&1; then
        run_privileged apk add "$package_name"
        return
    fi

    echo "No supported package manager found. Please install $package_name manually."
    exit 1
}

ensure_command() {
    command_name="$1"
    package_name="$2"

    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "$command_name not found. Installing..."
        install_package "$package_name"
    fi
}

ensure_command git git
ensure_command curl curl

set_env_value() {
    key="$1"
    value="$2"

    if grep -q "^${key}=" .env; then
        sed -i "s|^${key}=.*|${key}=${value}|" .env
    else
        echo "${key}=${value}" >> .env
    fi
}

if [ ! -f .env ]; then
    echo ".env file not found. Creating from .env.EXAMPLE..."
	cp .env.EXAMPLE .env
fi

if [ ! -f IDENTITY.md ]; then
    echo "IDENTITY.md file not found. Creating from IDENTITY.md.EXAMPLE..."
	cp IDENTITY.md.EXAMPLE IDENTITY.md
fi

source .env
echo "Installing UV Python"
curl -LsSf https://astral.sh/uv/install.sh | sh # installs uv python
echo "Installing dependencies..."
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
echo "LLM setup:"
echo "1) Download local model with LM Studio"
echo "2) Use remote LLM API key"
read -rp "Choose [1/2]: " llm_choice
llm_choice="${llm_choice:-2}"

if [ "$llm_choice" = "1" ]; then
    set_env_value ENABLE_LMSTUDIO true
    ENABLE_LMSTUDIO=true
    echo "Enabled ENABLE_LMSTUDIO=true in .env."

    if [ -n "$LLM_MODEL" ]; then
        echo "Installing LM Studio"
        curl -fsSL https://lmstudio.ai/install.sh | bash # installs lmstudio cli
        echo "Downloading and loading LLM model from .env: $LLM_MODEL"
        lms get "$LLM_MODEL" -y
        lms load "$LLM_MODEL"
    else
        echo "Local model setup requires LLM_MODEL in .env."
    fi
else
    set_env_value ENABLE_LMSTUDIO false
    ENABLE_LMSTUDIO=false
    echo "Disabled ENABLE_LMSTUDIO in .env."
    echo "Using remote LLM API key from .env."
fi
echo "Installation complete."
echo ""
echo "Before starting the service, review and edit these files if needed:"
echo " - $(pwd)/.env"
echo " - $(pwd)/IDENTITY.md"
echo ""
echo "1) Edit these files now and start manually later"
echo "2) Skip editing and start the service now"
read -rp "Choose [1/2]: " install_choice
install_choice="${install_choice:-2}"

if [ "$install_choice" = "1" ]; then
    echo "Alright! After you finish editing and saving, run ./start.sh manually."
    exit 0
fi

echo "Ok then. Proceeding without modifying the files."
echo "Some tools and Telegram will not work because there will be missing configurations."

./start.sh