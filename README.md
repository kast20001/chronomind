# ChronoMind

Demo calendar app with an AI-style assistant (rule-based parsing, no external APIs) -- just a canvas for a project

**Live demo:** https://kast20001.github.io/chronomind/

> Страница репозитория на GitHub показывает этот README. Само приложение открывается по ссылке выше (GitHub Pages).

## Features

- Month calendar view with colored events
- AI chat sidebar — create events from natural language (Russian/English)
- Manual event form, event details panel, delete
- Sample events seeded on startup (in-memory only)

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
python agent.py
```

Opens http://127.0.0.1:5000 in your browser.

Options:

```bash
python agent.py --no-browser
python agent.py --port 8080
```

## Example prompts

- `созвон с командой завтра в 15:00`
- `что сегодня?`
- `свободные слоты`
- `meeting with team on Friday at 10:00`

## Stack

- Python 3.10+
- Flask (single-file app: `agent.py`)
