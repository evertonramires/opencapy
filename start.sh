#!/bin/bash

source .env
if [ "$ENABLE_LMSTUDIO" = "true" ]; then
    echo "Loading LM Studio model: $LLM_MODEL"
    lms load "$LLM_MODEL"
fi
.venv/bin/python main.py