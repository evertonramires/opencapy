# Open Capy

[![Support my work ❤️](https://img.shields.io/badge/Support%20my%20work%20❤️-orange?style=for-the-badge&logo=patreon&logoColor=white)](https://www.patreon.com/c/evertonics)

This is a bare minimum AI agentic harness I created after giving up on openclaw cronjob not working properly. Main intent is to keep as simple as possible to be used as boiler plate for other agentic projects in the future.

## Requirements

This harness was devoloped on Ubuntu 24.04, using UV Python, LM Studio and google/gemma-4-26b-a4b model. This should work on a wide variety of different environments, but as a single person project, I can't test much, please test and open an issue if it doesn't work for your setup.

- Linux
- Python
- LM Studio or OpenAI standard compatible API, or the Claude Code CLI
- Tool calling capable model loaded

## Running on a Claude subscription

Instead of paying per token for an API key, Open Capy can run on the Claude Code CLI
under your Claude subscription.

```bash
npm install -g @anthropic-ai/claude-code
claude # run once and sign in with your subscription
```

Then set `ENABLE_CLAUDE_CODE=true` in `.env` and start as usual. Open Capy's tools are
handed to the CLI through `mcp_bridge.py`, an MCP server that re-exports every
`tools/*_tool.py`, so tool calling keeps working exactly as before. Claude Code's own
`Bash`, `Read`, `Write` and `WebSearch` tools are offered on top of them; trim that list
with `CLAUDE_CODE_BUILTIN_TOOLS` if you don't want the agent to have shell access.

Keep `LLM_API_HOST`, `LLM_API_KEY` and `LLM_MODEL` configured: whenever the CLI fails
(not logged in, usage limit reached, binary missing) Open Capy falls back to them
automatically.

### Usage window and the work buffer

A Claude subscription has a rolling 5 hour usage window, and Open Capy watches it so it
doesn't spend the whole thing talking to itself in the background.

Once the window is at least `USAGE_BUFFER_THRESHOLD_PERCENT` used (80 by default; set it to
100 to effectively turn this off, since then it only kicks in once the window is fully spent
and Claude would refuse the call anyway):

- Background work — triggered tasks, routines, the calendar digest, the Vikunja watcher,
  the daily focus and the date nudge — goes into a buffer in `hood/buffer.json` instead of
  being sent to Claude.
- You get one message saying how used the window is and when it resets. One per window, not
  one per heartbeat.
- Chatting still works: your messages route to the `LLM_*` settings (and then
  `FALLBACK_LLM_*`) instead of Claude, with all tools still available. So keep those
  configured, or chat above the threshold will fail.
- When the window resets the buffer drains on its own, one item per heartbeat, so the fresh
  window isn't burned in one go.

You can also park things there yourself with `/later`, for anything that is neither urgent
nor important right now — those always wait for the next window, whatever the current usage.

```code
/usage - how much of the 5 hour and 7 day windows is used, and when they reset
/model - get the current model; /model opus switches it
/effort - get the current reasoning effort; /effort high sets it (low, medium, high, xhigh, max, default)
/later tidy up my notes - queue something for the next usage window
/listbuffer - list the work waiting for the next window
/deletebuffer 3 - drop buffered item 3
```

The agent has the same abilities through its tools (`check_claude_usage`, `set_claude_model`,
`set_claude_effort`, `buffer_for_next_window`, `list_buffered_work`), so it can check the
window before starting something long, drop to a cheaper model when things get tight, or
decide on its own that a piece of work can wait. Model and effort changes apply from the next
message, since every reply runs in a fresh CLI session.

## Install

```bash
./install.sh
```

## Run

```bash
./start
```

## Manual Pre-Install

This step is just to help installing uv python and lm-studio on linux, if you're using a different environment, skip it.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh # installs uv python
curl -fsSL https://lmstudio.ai/install.sh | bash # installs lmstudio cli
lms get google/gemma-4-26b-a4b -y
lms load google/gemma-4-26b-a4b
```

## Manual Install

```bash
git clone https://github.com/evertonramires/opencapy.git
cd opencapy
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.EXAMPLE .env
cp IDENTITY.md.EXAMPLE IDENTITY.md
```

## Manual Run

Adjust .env and IDENTITY.md as wanted and then run:

```bash
source .venv/bin/activate
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

To-dos (Vikunja):

- Configure in `.env`: set `ENABLE_VIKUNJA=true`, `VIKUNJA_API_HOST` (e.g. `https://try.vikunja.io` or your self-hosted instance) and `VIKUNJA_API_TOKEN`.
- Create the API token in Vikunja under Settings > API Tokens, with permissions for tasks and projects — add labels and project views too if you want `ENABLE_TODO_TRIAGE`.
- Optional: `VIKUNJA_DEFAULT_PROJECT_ID` sets the project new to-dos go to (defaults to 1, usually the Inbox).
- Besides the manual commands below, the agent can manage to-dos on its own through the vikunja tool (add, list, complete, delete, and pick a project).
- The agent also watches Vikunja for to-dos you add outside the bot (web/mobile app) and briefly acknowledges them, and cheers you on when you complete a to-do — wherever you tick it off. `VIKUNJA_WATCH_INTERVAL_SECONDS` controls how often it checks (defaults to 30). The first check after enabling silently marks existing to-dos as known, so only to-dos added afterwards are announced (tracked in `hood/vikunja_seen.json`).
- The to-do features are designed to be ADHD-friendly: capturing is instant (no interrogation about details), and starting is helped by `/focus`, which picks exactly one to-do and suggests a first step small enough to take two minutes, offering a check-in afterwards.
- Optional: `VIKUNJA_DAILY_FOCUS_HOUR` (24h UTC hour, -1 disables) sends one gentle morning message with up to 3 to-dos that matter today and a suggested starter — never the whole list.
- Optional: `VIKUNJA_DATE_NUDGE_HOUR` (24h UTC hour, -1 disables) sends one daily message listing to-dos without a due date; reply with rough dates ("friday", "next week") and the agent sets them, keeping Vikunja's Gantt timeline useful.
- Optional: with `ENABLE_TODO_TRIAGE=true` every incoming to-do is sorted into the four urgent/important boxes and labelled with what else is true about it; run `/triagesetup` once to create the tags and a project per box. `VIKUNJA_DEFAULT_PROJECT_ID` then means strictly the unsorted Inbox. A weekly message reports how the boxes are shifting, on the same `WEEKLY_REVIEW_DAY` schedule as the stale sweep.
- Optional: with `ENABLE_TODO_DEDUPE=true` the same thing written down twice stops becoming two to-dos. Every capture is matched against the whole list first — on meaning, not on wording, so "dentist" finds "Call the dentist about the cleaning" and accents, plurals and typos don't hide a match. When one already exists nothing is created: the agent merges whatever the second telling added (a detail, a date, a name, a better phrasing) into the to-do you already have as a dated line, or just tells you where it already is. A to-do you finished in the last `TODO_DUPLICATE_DONE_DAYS` still counts, so a chore you just did doesn't quietly come back. `TODO_DUPLICATE_THRESHOLD` (0 to 1, defaults to 0.55) sets how alike two to-dos have to read; it leans towards catching too much rather than too little, because the refused capture is always offered straight back with an **Add it anyway** button. To-dos written directly in Vikunja are checked too, and come with a **Merge into** button instead, since by then the second one exists.
- Optional: with `ENABLE_VIKUNJA_SUBTASKS=true` the agent breaks multi-step to-dos into steps (on its own or when asked), written as a tickable checklist inside that to-do's own description. The steps stay inside the task rather than becoming separate to-dos, so the list never gets longer — a list that doubles in length is the thing that makes you stop opening it. Tick the boxes in the Vikunja app and the to-do's progress bar fills on its own.

```code
/focus - pick one to-do to start now, with a tiny first step
/addtodo Buy groceries - add a to-do
/listtodos - list pending to-dos
/listtodos all - list all to-dos including done ones
/donetodo 12 - mark to-do with id 12 as done
/deletetodo 12 - delete to-do with id 12
/mergetodo 31 12 - fold to-do 31 into to-do 12 and remove the duplicate
```

Knowledge base (AppFlowy):

- Configure in `.env`: set `ENABLE_APPFLOWY=true`, `APPFLOWY_API_HOST` (e.g. `https://beta.appflowy.cloud` or your self-hosted instance), `APPFLOWY_EMAIL` and `APPFLOWY_PASSWORD`.
- AppFlowy has no API tokens, so the agent logs in with your credentials and caches the refresh token in `hood/appflowy_token.json`.
- Optional: `APPFLOWY_WORKSPACE_ID` (defaults to your first workspace) and `APPFLOWY_DEFAULT_DATABASE_ID` (the database new rows go to when the agent isn't told which one).
- AppFlowy is the shared knowledge base, Vikunja stays the to-do list. There are no manual commands; the agent uses it through its tools: list databases, list and add database rows, update a row it created, list pages, read a page, create a page, append text to a page, and move a page to trash.
- Pages are read back as markdown — headings, bullets, checkboxes and quotes are all preserved — so the agent can look at a report or schema you wrote and work from it.
- Two limits come from the AppFlowy API itself, and the agent is told about each one:
  - **Page content is append-only.** New blocks can be added to the end of a page, but existing blocks cannot be edited or removed. To revise a page the agent reads it, then appends a correction or replaces the page.
  - **Database rows cannot be deleted, and can only be changed by the agent if it created them.** Row updates go through an upsert keyed by the value the row was created with, so rows you add in the AppFlowy app are readable but not editable. Pages have no such limit — they can be renamed and trashed.

Voice notes (Telegram):

- Set `ENABLE_TRANSCRIPTION=true` in `.env` and talk to the bot by holding the mic button; forwarded audio files work the same way.
- No extra credentials and no ffmpeg: transcription rides on the `LLM_API_HOST` and `LLM_API_KEY` you already configured, as long as that endpoint serves `/v1/audio/transcriptions` (an OpenAI-compatible gateway, LM Studio being the usual exception).
- `TRANSCRIPTION_MODEL` picks the model, defaulting to `groq/whisper-large-v3-turbo`. The language is detected automatically, no configuration needed.
- The transcript is echoed back as a 🎤 message before the agent replies, so a mishearing is visible instead of the agent quietly acting on the wrong words.
- Transcripts are handed to the agent as plain text, so anything you can type you can also say — including commands.

Tools:

```code
/listtools - list all available tools
```

Google Calendar:

- Configure OAuth in `.env`: `CALENDAR_ID`, `CALENDAR_OAUTH_CLIENT_ID`, `CALENDAR_OAUTH_CLIENT_SECRET`, `CALENDAR_OAUTH_REDIRECT_URI`.
- `CALENDAR_OAUTH_REDIRECT_URI` is independent from `CHAT_API_HOST`, so you can keep the API local and point only the OAuth callback to a temporary HTTPS tunnel.
- In Google Cloud Console, add your redirect URI (for example `http://localhost:8000/oauth/calendar/callback`) to your OAuth client.
- Start OAuth using `/calendarauth`, then open the auth link returned by Capy.
- If callback host is localhost, open the OAuth link on the same machine running Capy.
- If callback host is not localhost, make sure that callback host address is reachable by the device opening the OAuth popup.
- After Google redirects back to callback, refresh token is validated and saved automatically in `hood/calendar_oauth.json`.
- Optional defaults: `CALENDAR_DEFAULT_DAYS_AHEAD`, `CALENDAR_DEFAULT_MAX_RESULTS`.
- Once a day (from `CALENDAR_DAILY_CHECK_HOUR`) the agent messages you today's events — only when there are any; empty days stay silent.
- Manual calendar commands:

```code
/calendarauth - start OAuth and get clickable auth link
/listcalendar - list upcoming events using defaults from .env
/listcalendar 14 20 - list 20 events for the next 14 days
/addcalendarevent Team sync | 2026-04-25T14:00:00Z | 2026-04-25T14:30:00Z | Weekly check-in
/deletecalendarevent <event_id>
```

Identity:

```code
/readidentity - read the current identity information
/writeidentity <content> - update the entire identity information
```

Claude subscription (see [Usage window and the work buffer](#usage-window-and-the-work-buffer)):

```code
/usage - how much of the 5 hour and 7 day windows is used, and when they reset
/model opus - switch model; /model alone reports it, /model default restores the .env one
/effort high - set reasoning effort (low, medium, high, xhigh, max, default)
/later tidy up my notes - queue something for the next usage window
/listbuffer - list the work waiting for the next window
/deletebuffer 3 - drop buffered item 3
```

Misc:

```code
/model - get the current model being used
/help - get the content of this README file
```

Human escalation:

```code
/listpending - list pending human guidance tasks
/answer 3 proceed with option A - answer pending task id 3
```

Focus sprints (`ENABLE_SPRINTS=true`):

```code
/sprint 12 - start a 25 minute sprint on to-do 12 (add a number for a different length)
/sprintdone 3 - finish sprint 3 and tick the to-do off
/sprintmore 3 10 - add 10 more minutes
/sprintstuck 3 - say you're stuck, and get help shrinking it
/low - low energy, get the smallest thing on your list
/shrink 12 - rewrite to-do 12 into one smaller step
/snooze 12 7 - push to-do 12 out by 7 days
```

Steering a to-do from Vikunja (`ENABLE_TODO_COMMENTS=true`):

Leave a comment on any to-do and Capy picks it up, does what you asked (moves the
date, adds detail, breaks it into steps, goes and researches it) and replies in the
same thread, signed, so the conversation about a task stays on the task. You get a
short heads-up in chat too. It only fetches the threads of tasks that actually
changed, so a quiet list costs one request.

Better titles (`ENABLE_TODO_RETITLE=true`):

A to-do jotted down as "dentist" is a decision you have to make again every time you
see it. Capy rewrites vague titles into the first concrete action — "Call the dentist
to book a cleaning" — using only what you actually wrote, and leaves clear ones alone.
The acknowledgement carries an **Undo** button, and your original is kept either way.

```code
/retitle 12 - rewrite to-do 12's title as a clear first action
/undotitle 12 - put your own title back
```

Triage (`ENABLE_TODO_TRIAGE=true`):

Every to-do that arrives gets sorted into the four urgent/important boxes and tagged
with what else is true about it — whether an AI, someone you could hire or a product
could take it off you, whether it's really a project in disguise, whether it's a
two-minute job, and what it needs from you to get done. A "drop" verdict is only ever
offered as a button; Capy never deletes anything on its own.

Run `/triagesetup` once and each box becomes **its own project** — Do, Schedule,
Delegate, Drop — leaving the Inbox as strictly the pile of things not yet sorted, so
its length tells you how far behind triage is. Filing a to-do moves it into that
project and Vikunja files the card into that project's own To-Do / Doing / Done board.
The box is also kept as a tag, so you can still filter by quadrant from anywhere.

```code
/triagesetup - create the tags and the four box projects in Vikunja
/triage 12 - sort to-do 12 into a box
/triageall - sort everything still in the Inbox
/quadrant 12 schedule - move to-do 12 to another box by hand
```

Timeline (`ENABLE_VIKUNJA` on, no extra setting):

Every to-do gets a start date of when it was created, and an end date of when you
ticked it done — so the Gantt view shows how long each thing actually took, rather
than being empty. To-dos with a due date get a planned bar too. Vikunja draws a bar
between start and end, which is why both are needed.

When a sprint's time is up you get a message with **Done / +10 min / Stuck** buttons,
so answering is one tap.

Autopilot (`ENABLE_AUTOPILOT=true`):

When you add a to-do, Capy decides whether it can move it forward on its own. If it
can, it researches it in the background and writes what it found into the to-do
description under a "🔎 Capy notes" heading, then tells you the one useful fact and
the one small next step. Anything you wrote yourself is never overwritten.

```code
/autopilot - show what's queued and how much of today's budget is left
```

It only takes on things it can genuinely do alone (finding a phone number, checking
opening hours, comparing prices, gathering links, drafting a message). It is capped at
`AUTOPILOT_MAX_PER_DAY` and pauses entirely while the usage window is nearly spent.

Approvals:

Emails and SMS are never sent straight away. Capy drafts them and sends you a card
with **Send / Change / Drop** buttons. Tapping Change lets you just say what to fix,
by text or voice note, and it redrafts.

```code
/listapprovals - list drafts waiting on you
/approve 1 - send draft 1
/reject 1 - drop draft 1
/tweak 1 make it shorter - redraft it
```

Approving runs exactly the message you saw, with no model in between, so what goes out
is what you approved. Drafts nobody answers expire after `APPROVAL_EXPIRY_HOURS`.
Widen the gate to other tools with `APPROVAL_REQUIRED_TOOLS`.

Weekly review (`WEEKLY_REVIEW_DAY=6` for Sunday):

Once a week Capy offers up to 3 to-dos nobody has touched in `STALE_TODO_DAYS`, each
with **Make it smaller / Next week / Drop it** buttons, and sends a short note about
what you actually finished that week.

## Chat API docs

With chat API running, navigate to:
[http://localhost:8000/docs](http://localhost:8000/docs)

> Disclaimer: This is a bare minimum project, bring your own security layer.
