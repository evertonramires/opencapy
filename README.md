# Open Capy

[![Support my work ❤️](https://img.shields.io/badge/Support%20my%20work%20❤️-orange?style=for-the-badge&logo=patreon&logoColor=white)](https://www.patreon.com/c/evertonics)

This is a bare minimum AI agentic harness I created after giving up on openclaw cronjob not working properly. Main intent is to keep as simple as possible to be used as boiler plate for other agentic projects in the future.

## Requirements

- LM Studio or OpenAI API compatible API
- Tool calling capable model loaded

## Pre-Install

This step is just to help installing uv python and lm-studio on linux, if you're using a different environment, skip it.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://lmstudio.ai/install.sh | bash
```

## Install

```bash
git clone https://github.com/evertonramires/opencapy.git
cd opencapy
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

1) Use telegram bot or
2) Navigate to [Chat Page](http://localhost:8000/) and
3) Just chat around or use one of the commands below.

### Commands

Tasks/Reminders:

```code
/addtask remember me to take a shower in 15 minutes from now - add a task
/listtasks - list all tasks
/deletetask 3 - delete task with id 3
```

Routines (recurring tasks):

```code
/addroutine take medication every day at 8am - add a recurring routine
/listroutines - list all routines
/deleteroutine 2 - delete routine with id 2
```

Notes:

```code
/addnote User likes blue color - add a note
/listnotes - list all notes
/deletenote 3 - delete note with id 3
```

Tools:

```code
/listtools - list all available tools
```

Identity:

```code
/readidentity - read the current identity information
/writeidentity <content> - update the entire identity information
```

Misc:

```code
/model - get the current model being used
/help - get the content of this README file
```

## Chat API docs

With chat API running, navigate to:
[http://localhost:8000/docs](http://localhost:8000/docs)

> Disclaimer: This is a bare minimum project, bring your own security layer.
