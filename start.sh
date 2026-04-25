#!/bin/bash

source .env
if [ "$ENABLE_LMSTUDIO" = "true" ]; then
    echo "Loading LM Studio model: $LLM_MODEL"
    lms load "$LLM_MODEL"
fi
source .venv/bin/activate
python main.py