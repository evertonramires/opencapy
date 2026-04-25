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
./start.sh