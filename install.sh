#!/bin/bash

if [ ! -f .env ]; then
    echo ".env file not found. Creating from .env.EXAMPLE..."
	cp .env.EXAMPLE .env
fi

if [ ! -f IDENTITY.md ]; then
    echo "IDENTITY.md file not found. Creating from IDENTITY.md.EXAMPLE..."
	cp IDENTITY.md.EXAMPLE IDENTITY.md
fi

source .env
if [ "$ENABLE_LMSTUDIO" = "true" ] && [ -n "$LLM_MODEL" ]; then
    echo "Installing LM Studio"
    curl -fsSL https://lmstudio.ai/install.sh | bash # installs lmstudio cli
    echo "Downloading and loading LLM model from .env: $LLM_MODEL"
    lms get "$LLM_MODEL" -y
    lms load "$LLM_MODEL"
fi
echo "Installing UV Python"
curl -LsSf https://astral.sh/uv/install.sh | sh # installs uv python
echo "Installing dependencies..."
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

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