#!/bin/bash

echo "Are you sure you want to uninstall OpenCapy? This will remove all installed dependencies and files. (y/n): "
read -r response
if [ "$response" != "y" ] && [ "$response" != "Y" ] && [ "$response" != "yes" ] && [ "$response" != "YES" ]; then
    echo "Uninstallation cancelled."
    exit 0
fi
echo "Stopping the application..."
./stop.sh

echo "Uninstalling dependencies..."
uv pip uninstall -r requirements.txt -y
if [ -f .env ]; then
    source .env
fi
if [ "$ENABLE_LMSTUDIO" = "true" ] && [ -n "$LLM_MODEL" ]; then
    echo "Should LM Studio be uninstalled as well? This will remove the LM Studio CLI and all downloaded models. (y/n): "
    read -r lm_response
    if [ "$lm_response" != "y" ] && [ "$lm_response" != "Y" ] && [ "$lm_response" != "yes" ] && [ "$lm_response" != "YES" ]; then
        echo "Skipping LM Studio uninstallation."
    else
        echo "Unloading LM Studio model: $LLM_MODEL"
        lms unload "$LLM_MODEL"
        echo "Uninstalling LM Studio"
        rm -f "$HOME/.local/bin/lms"
        rm -f "$HOME/.local/bin/llmster"
        rm -rf "$HOME/.lmstudio"
    fi
fi

echo "Should UV Python be uninstalled as well? This will remove the UV CLI and virtual environments. (y/n): "
read -r uv_response
if [ "$uv_response" != "y" ] && [ "$uv_response" != "Y" ] && [ "$uv_response" != "yes" ] && [ "$uv_response" != "YES" ]; then
    echo "Skipping UV Python uninstallation."
else
    echo "Uninstalling UV Python"
    rm -f "$HOME/.local/bin/uv"
    rm -f "$HOME/.local/bin/uvx"
    rm -f "$HOME/.cargo/bin/uv"
    rm -f "$HOME/.cargo/bin/uvx"
    echo "Removing virtual environment..."
    rm -rf .venv
fi

echo "Should .env and IDENTITY.md be removed as well? (y/n): "
read -r env_response
if [ "$env_response" != "y" ] && [ "$env_response" != "Y" ] && [ "$env_response" != "yes" ] && [ "$env_response" != "YES" ]; then
    echo "Skipping .env and IDENTITY.md removal."
else
    echo "Removing .env and IDENTITY.md file..."
    rm -f .env
    rm -f IDENTITY.md
fi

echo "Should memory, notes and all operation files be cleaned as well? This will remove all operation data. (y/n): "
read -r hood_response
if [ "$hood_response" != "y" ] && [ "$hood_response" != "Y" ] && [ "$hood_response" != "yes" ] && [ "$hood_response" != "YES" ]; then
    echo "Skipping operation data cleanup."
else
    echo "Cleaning operation data files..."
    rm -rf hood
    mkdir hood
    touch hood/empty
fi

echo "Done. So Long, and Thanks for All the Fish. 🐟"