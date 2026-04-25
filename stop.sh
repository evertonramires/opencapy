#!/bin/bash

echo "Stopping the application..."

if [ -f .env ]; then
	source .env
fi

echo "Stopping main.py process..."
pkill -f "python main.py"

if [ "$ENABLE_LMSTUDIO" = "true" ] && [ -n "$LLM_MODEL" ]; then
	echo "Unloading LM Studio model: $LLM_MODEL"
	lms unload "$LLM_MODEL"
fi

pgrep -af uvicorn
pkill -f uvicorn

echo "Application stopped."
