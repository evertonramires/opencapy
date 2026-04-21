# Open Capy

[![Support my work ❤️](https://img.shields.io/badge/Support%20my%20work%20❤️-orange?style=for-the-badge&logo=patreon&logoColor=white)](https://www.patreon.com/c/evertonics)

This is a bare minimum AI agentic harness I created after giving up on openclaw cronjob not working properly. Main intent is to keep as simple as possible to be used as boiler plate for other agentic projects in the future.

## Requirements

- LM Studio or OpenAI API compatible API
- Tool calling capable model loaded

## Install

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.EXAMPLE .env
cp IDENTITY.md.EXAMPLE IDENTITY.md
```

## Run

Adjust .env and IDENTITY.md as wanted and then run:

```bash
uv run main.py
```

## Use

Just chat around or use one of the commands below.

### Commands

Tasks/Reminders:

```code
/addtask remember me to take a shower in 15 minutes from now - add a task
/listtasks - list all tasks
/deletetask 3 - delete task with id 3
```

Notes:

```code
/addnote User likes blue color - add a note
/listnotes - list all notes
/deletenote 3 - delete note with id 3
```
