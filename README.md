# opencapy

## Install

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.EXAMPLE .env
cp IDENTITY.md.EXAMPLE IDENTITY.md
```

## Run

```bash
uv run main.py
```

## Use

Just chat around or use one of the commands below.

### Commands

Tasks/Reminders:

```code
/add remember me to take a shower in 15 minutes from now - add a task
/list - list all tasks
/delete 3 - delete task with id 3
```
