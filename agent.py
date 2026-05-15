"""
ChronoMind — демо календаря с ИИ-ассистентом.
Запуск: python agent.py  →  http://127.0.0.1:5000
"""

from __future__ import annotations

import argparse
import calendar
import re
import uuid
import webbrowser
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from threading import Timer
from typing import Any

from flask import Flask, jsonify, render_template_string, request

# ---------------------------------------------------------------------------
# Модель и «ИИ» (правила + шаблоны, без внешних API)
# ---------------------------------------------------------------------------

COLORS = ("#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6")


@dataclass
class CalendarEvent:
    id: str
    title: str
    start: str  # ISO date YYYY-MM-DD
    end: str
    time: str  # HH:MM или пусто = весь день
    duration_min: int
    location: str
    description: str
    color: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AppState:
    events: list[CalendarEvent] = field(default_factory=list)

    def seed(self) -> None:
        today = date.today()
        samples = [
            ("Стендап команды", 0, "10:00", 30, "Zoom", "Ежедневный sync"),
            ("Ревью дизайна", 1, "14:00", 60, "Конференц-зал B", "Макеты v2"),
            ("Обед с клиентом", 3, "12:30", 90, "Café Noir", ""),
            ("Демо продукта", 7, "16:00", 45, "Онлайн", "Презентация Q2"),
            ("Йога", 2, "08:00", 60, "Дома", ""),
        ]
        for i, (title, day_offset, time, dur, loc, desc) in enumerate(samples):
            d = today + timedelta(days=day_offset)
            self.events.append(
                CalendarEvent(
                    id=str(uuid.uuid4())[:8],
                    title=title,
                    start=d.isoformat(),
                    end=d.isoformat(),
                    time=time,
                    duration_min=dur,
                    location=loc,
                    description=desc,
                    color=COLORS[i % len(COLORS)],
                )
            )


STATE = AppState()
STATE.seed()

RU_MONTHS = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)
RU_WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


def _parse_relative_day(text: str, base: date) -> date | None:
    t = text.lower()
    if "сегодня" in t or "today" in t:
        return base
    if "завтра" in t or "tomorrow" in t:
        return base + timedelta(days=1)
    if "послезавтра" in t:
        return base + timedelta(days=2)
    m = re.search(r"через\s+(\d+)\s+дн", t)
    if m:
        return base + timedelta(days=int(m.group(1)))
    for i, wd in enumerate(RU_WEEKDAYS):
        if wd.lower() in t or calendar.day_name[i].lower() in t:
            delta = (i - base.weekday()) % 7
            if delta == 0:
                delta = 7
            return base + timedelta(days=delta)
    m = re.search(r"(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?", t)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        y = int(m.group(3)) if m.group(3) else base.year
        if y < 100:
            y += 2000
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    return None


def _parse_time(text: str) -> str | None:
    t = text.lower()
    m = re.search(r"(\d{1,2})[:.](\d{2})", t)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    m = re.search(r"в\s+(\d{1,2})(?:\s*час|\s*:\d{2})?", t)
    if m:
        return f"{int(m.group(1)):02d}:00"
    m = re.search(r"at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", t, re.I)
    if m:
        h = int(m.group(1))
        mins = m.group(2) or "00"
        ampm = (m.group(3) or "").lower()
        if ampm == "pm" and h < 12:
            h += 12
        if ampm == "am" and h == 12:
            h = 0
        return f"{h:02d}:{mins}"
    return None


def _parse_duration(text: str) -> int:
    m = re.search(r"(\d+)\s*(?:мин|min)", text.lower())
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*(?:час|hr|h)\b", text.lower())
    if m:
        return int(m.group(1)) * 60
    return 60


def ai_parse_message(text: str, base: date | None = None) -> tuple[str, CalendarEvent | None]:
    """Возвращает (ответ ассистента, событие или None)."""
    base = base or date.today()
    clean = text.strip()
    if not clean:
        return "Напишите, что запланировать — например: «встреча с Анной завтра в 15:00».", None

    lower = clean.lower()
    if any(w in lower for w in ("привет", "hello", "hi", "здравств")):
        return (
            "Привет! Я ChronoMind. Могу создать событие, показать расписание "
            "или подсказать свободные слоты. Попробуйте: «созвон с командой в пятницу в 10:00».",
            None,
        )
    if any(w in lower for w in ("расписание", "что сегодня", "what today", "покажи день")):
        target = _parse_relative_day(lower, base) or base
        day_events = [e for e in STATE.events if e.start == target.isoformat()]
        if not day_events:
            return f"На {target.strftime('%d.%m.%Y')} событий нет — день свободен.", None
        lines = [f"• {e.time or 'весь день'} — {e.title}" for e in sorted(day_events, key=lambda x: x.time)]
        return f"Расписание на {target.strftime('%d.%m.%Y')}:\n" + "\n".join(lines), None
    if "свободн" in lower or "free slot" in lower:
        return (
            "Свободные окна сегодня: 09:00–10:00, 11:30–12:30, 15:00–16:00. "
            "(демо-ответ — в проде здесь был бы анализ календаря)",
            None,
        )

    # Создание события
    if not any(w in lower for w in ("создай", "добав", "заплан", "встреч", "созвон", "meeting", "call", "event")):
        # Всё равно пробуем распарсить как событие
        pass

    title = clean
    for prefix in (
        r"^(?:создай|добавь|запланируй)\s+",
        r"^(?:встречу|созвон|событие)\s+",
        r"^meeting\s+",
    ):
        title = re.sub(prefix, "", title, flags=re.I).strip()

    # Вырезаем дату/время из заголовка
    event_date = _parse_relative_day(lower, base) or base
    event_time = _parse_time(lower)
    duration = _parse_duration(lower)

    # Упрощённый заголовок
    title = re.sub(
        r",?\s*(?:завтра|сегодня|послезавтра|в\s+\d{1,2}[:.]\d{2}|at\s+\d+).*",
        "",
        title,
        flags=re.I,
    ).strip(" ,.")
    if len(title) < 3:
        title = "Новое событие"

    loc_m = re.search(r"(?:в|@|at)\s+([A-Za-zА-Яа-я0-9\s\-]+?)(?:\s+завтра|\s+в\s+\d|$)", clean, re.I)
    location = loc_m.group(1).strip() if loc_m else ""

    ev = CalendarEvent(
        id=str(uuid.uuid4())[:8],
        title=title[:80],
        start=event_date.isoformat(),
        end=event_date.isoformat(),
        time=event_time or "",
        duration_min=duration,
        location=location[:60],
        description="Создано ассистентом ChronoMind",
        color=COLORS[len(STATE.events) % len(COLORS)],
    )
    day_label = f"{event_date.day} {RU_MONTHS[event_date.month - 1]}"
    time_label = event_time or "весь день"
    reply = f"Готово — добавил «{ev.title}» на {day_label}, {time_label}."
    if location:
        reply += f" Место: {location}."
    return reply, ev


# ---------------------------------------------------------------------------
# Flask
# ---------------------------------------------------------------------------

app = Flask(__name__)

HTML = r"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ChronoMind — календарь с ИИ</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700&display=swap" rel="stylesheet" />
  <style>
    :root {
      --bg: #0f1117;
      --surface: #181b24;
      --surface2: #1f2430;
      --border: #2a3142;
      --text: #e8eaef;
      --muted: #8b93a7;
      --accent: #6366f1;
      --accent-hover: #818cf8;
      --success: #10b981;
      --radius: 12px;
      --shadow: 0 8px 32px rgba(0,0,0,.45);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: "DM Sans", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: flex;
    }
    .sidebar {
      width: 380px;
      min-width: 320px;
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      background: var(--surface);
    }
    .brand {
      padding: 20px 20px 12px;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .logo {
      width: 36px; height: 36px;
      background: linear-gradient(135deg, var(--accent), #a855f7);
      border-radius: 10px;
      display: grid; place-items: center;
      font-weight: 700; font-size: 14px;
    }
    .brand h1 { font-size: 1.1rem; font-weight: 600; }
    .brand p { font-size: 0.75rem; color: var(--muted); }
    .ai-badge {
      margin: 0 20px 12px;
      padding: 8px 12px;
      background: rgba(99,102,241,.12);
      border: 1px solid rgba(99,102,241,.25);
      border-radius: 8px;
      font-size: 0.8rem;
      color: #a5b4fc;
    }
    .chat {
      flex: 1;
      overflow-y: auto;
      padding: 0 16px 12px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .msg {
      max-width: 92%;
      padding: 10px 14px;
      border-radius: 14px;
      font-size: 0.88rem;
      line-height: 1.45;
      white-space: pre-wrap;
    }
    .msg.bot {
      align-self: flex-start;
      background: var(--surface2);
      border: 1px solid var(--border);
    }
    .msg.user {
      align-self: flex-end;
      background: var(--accent);
      color: #fff;
    }
    .msg.thinking { opacity: .6; font-style: italic; }
    .chat-input {
      padding: 16px;
      border-top: 1px solid var(--border);
      display: flex;
      gap: 8px;
    }
    .chat-input input {
      flex: 1;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px 14px;
      color: var(--text);
      font: inherit;
      outline: none;
    }
    .chat-input input:focus { border-color: var(--accent); }
    .chat-input button {
      background: var(--accent);
      border: none;
      color: #fff;
      border-radius: 10px;
      padding: 0 16px;
      cursor: pointer;
      font: inherit;
      font-weight: 600;
    }
    .chat-input button:hover { background: var(--accent-hover); }
    .main {
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .toolbar {
      padding: 16px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid var(--border);
    }
    .toolbar h2 { font-size: 1.35rem; font-weight: 600; }
    .toolbar-actions { display: flex; gap: 8px; align-items: center; }
    .btn {
      background: var(--surface2);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 8px 14px;
      border-radius: 8px;
      cursor: pointer;
      font: inherit;
      font-size: 0.85rem;
    }
    .btn:hover { border-color: var(--muted); }
    .btn.primary {
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }
    .btn.primary:hover { background: var(--accent-hover); }
    .cal-wrap {
      flex: 1;
      padding: 20px 24px 24px;
      overflow: auto;
    }
    .weekdays {
      display: grid;
      grid-template-columns: repeat(7, 1fr);
      gap: 6px;
      margin-bottom: 8px;
    }
    .weekdays span {
      text-align: center;
      font-size: 0.75rem;
      color: var(--muted);
      font-weight: 500;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(7, 1fr);
      gap: 6px;
    }
    .day {
      min-height: 100px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 8px;
      cursor: pointer;
      transition: border-color .15s, transform .1s;
    }
    .day:hover { border-color: var(--accent); }
    .day.other { opacity: .35; }
    .day.today { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
    .day.selected { background: rgba(99,102,241,.08); border-color: var(--accent); }
    .day-num {
      font-size: 0.8rem;
      font-weight: 600;
      margin-bottom: 6px;
      color: var(--muted);
    }
    .day.today .day-num { color: var(--accent); }
    .pill {
      font-size: 0.68rem;
      padding: 3px 6px;
      border-radius: 4px;
      margin-bottom: 3px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      color: #fff;
      cursor: pointer;
    }
    .pill:hover { filter: brightness(1.1); }
    .more { font-size: 0.65rem; color: var(--muted); margin-top: 2px; }
    .detail-panel {
      position: fixed;
      right: 0; top: 0; bottom: 0;
      width: 360px;
      background: var(--surface);
      border-left: 1px solid var(--border);
      box-shadow: var(--shadow);
      transform: translateX(100%);
      transition: transform .25s ease;
      z-index: 50;
      display: flex;
      flex-direction: column;
    }
    .detail-panel.open { transform: translateX(0); }
    .detail-header {
      padding: 20px;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
    }
    .detail-header h3 { font-size: 1.1rem; max-width: 260px; }
    .detail-body { padding: 20px; flex: 1; overflow-y: auto; }
    .detail-body dt { font-size: 0.72rem; color: var(--muted); text-transform: uppercase; margin-top: 14px; }
    .detail-body dd { margin-top: 4px; font-size: 0.9rem; }
    .detail-actions {
      padding: 16px 20px;
      border-top: 1px solid var(--border);
      display: flex;
      gap: 8px;
    }
    .detail-actions .btn.danger { color: #f87171; border-color: #7f1d1d; }
    .overlay {
      position: fixed; inset: 0;
      background: rgba(0,0,0,.4);
      opacity: 0; pointer-events: none;
      transition: opacity .25s;
      z-index: 40;
    }
    .overlay.show { opacity: 1; pointer-events: auto; }
    .modal {
      position: fixed;
      left: 50%; top: 50%;
      transform: translate(-50%, -50%) scale(.95);
      opacity: 0;
      pointer-events: none;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 24px;
      width: min(420px, 92vw);
      z-index: 60;
      transition: opacity .2s, transform .2s;
    }
    .modal.show { opacity: 1; pointer-events: auto; transform: translate(-50%, -50%) scale(1); }
    .modal h3 { margin-bottom: 16px; }
    .field { margin-bottom: 12px; }
    .field label { display: block; font-size: 0.75rem; color: var(--muted); margin-bottom: 4px; }
    .field input, .field textarea {
      width: 100%;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px 12px;
      color: var(--text);
      font: inherit;
    }
    .field textarea { resize: vertical; min-height: 60px; }
    .modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
    .suggestions {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      padding: 0 16px 8px;
    }
    .suggestions button {
      font-size: 0.72rem;
      padding: 6px 10px;
      border-radius: 20px;
      border: 1px solid var(--border);
      background: transparent;
      color: var(--muted);
      cursor: pointer;
    }
    .suggestions button:hover { border-color: var(--accent); color: var(--text); }
    @media (max-width: 900px) {
      body { flex-direction: column; }
      .sidebar { width: 100%; max-height: 45vh; border-right: none; border-bottom: 1px solid var(--border); }
    }
  </style>
</head>
<body>
  <aside class="sidebar">
    <div class="brand">
      <div class="logo">CM</div>
      <div>
        <h1>ChronoMind</h1>
        <p>Календарь с ИИ-ассистентом</p>
      </div>
    </div>
    <div class="ai-badge">● ИИ онлайн — демо без внешних API</div>
    <div class="suggestions" id="suggestions"></div>
    <div class="chat" id="chat"></div>
    <form class="chat-input" id="chatForm">
      <input type="text" id="chatInput" placeholder="Например: созвон завтра в 15:00" autocomplete="off" />
      <button type="submit">→</button>
    </form>
  </aside>

  <main class="main">
    <header class="toolbar">
      <div>
        <button class="btn" id="prevMonth">‹</button>
        <button class="btn" id="todayBtn" style="margin:0 6px">Сегодня</button>
        <button class="btn" id="nextMonth">›</button>
        <h2 id="monthLabel" style="display:inline;margin-left:12px"></h2>
      </div>
      <div class="toolbar-actions">
        <button class="btn primary" id="newEventBtn">+ Событие</button>
      </div>
    </header>
    <div class="cal-wrap">
      <div class="weekdays" id="weekdays"></div>
      <div class="grid" id="grid"></div>
    </div>
  </main>

  <div class="overlay" id="overlay"></div>
  <aside class="detail-panel" id="detailPanel">
    <div class="detail-header">
      <h3 id="detailTitle">—</h3>
      <button class="btn" id="closeDetail">✕</button>
    </div>
    <dl class="detail-body" id="detailBody"></dl>
    <div class="detail-actions">
      <button class="btn danger" id="deleteEvent">Удалить</button>
      <button class="btn" id="closeDetail2">Закрыть</button>
    </div>
  </aside>

  <div class="modal" id="modal">
    <h3>Новое событие</h3>
    <form id="eventForm">
      <div class="field"><label>Название</label><input name="title" required /></div>
      <div class="field"><label>Дата</label><input name="date" type="date" required /></div>
      <div class="field"><label>Время (пусто = весь день)</label><input name="time" type="time" /></div>
      <div class="field"><label>Место</label><input name="location" /></div>
      <div class="field"><label>Описание</label><textarea name="description"></textarea></div>
      <div class="modal-actions">
        <button type="button" class="btn" id="cancelModal">Отмена</button>
        <button type="submit" class="btn primary">Сохранить</button>
      </div>
    </form>
  </div>

<script>
const RU_MONTHS = ["Январь","Февраль","Март","Апрель","Май","Июнь","Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"];
const WEEKDAYS = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"];

let viewYear, viewMonth, selectedDate, events = [], selectedEventId = null;

function iso(d) {
  return d.getFullYear() + "-" + String(d.getMonth()+1).padStart(2,"0") + "-" + String(d.getDate()).padStart(2,"0");
}

function init() {
  const t = new Date();
  viewYear = t.getFullYear();
  viewMonth = t.getMonth();
  selectedDate = iso(t);
  document.getElementById("weekdays").innerHTML = WEEKDAYS.map(w => `<span>${w}</span>`).join("");
  document.querySelector("#eventForm [name=date]").value = selectedDate;
  loadEvents();
  seedChat();
  bindUI();
}

function seedChat() {
  addMsg("bot", "Добро пожаловать в ChronoMind! Спросите расписание или опишите встречу — я добавлю её в календарь.");
  const hints = ["Что сегодня?", "Созвон в пятницу в 10:00", "Свободные слоты", "Демо продукта послезавтра в 16:00"];
  const box = document.getElementById("suggestions");
  hints.forEach(h => {
    const b = document.createElement("button");
    b.textContent = h;
    b.onclick = () => { document.getElementById("chatInput").value = h; document.getElementById("chatForm").requestSubmit(); };
    box.appendChild(b);
  });
}

function bindUI() {
  document.getElementById("prevMonth").onclick = () => { viewMonth--; if (viewMonth < 0) { viewMonth = 11; viewYear--; } render(); };
  document.getElementById("nextMonth").onclick = () => { viewMonth++; if (viewMonth > 11) { viewMonth = 0; viewYear++; } render(); };
  document.getElementById("todayBtn").onclick = () => {
    const t = new Date();
    viewYear = t.getFullYear(); viewMonth = t.getMonth(); selectedDate = iso(t); render();
  };
  document.getElementById("newEventBtn").onclick = () => openModal();
  document.getElementById("cancelModal").onclick = closeModal;
  document.getElementById("overlay").onclick = () => { closeModal(); closeDetail(); };
  document.getElementById("closeDetail").onclick = closeDetail;
  document.getElementById("closeDetail2").onclick = closeDetail;
  document.getElementById("deleteEvent").onclick = deleteSelected;
  document.getElementById("eventForm").onsubmit = saveManualEvent;
  document.getElementById("chatForm").onsubmit = sendChat;
}

async function loadEvents() {
  const r = await fetch("/api/events");
  events = await r.json();
  render();
}

function render() {
  document.getElementById("monthLabel").textContent = RU_MONTHS[viewMonth] + " " + viewYear;
  const first = new Date(viewYear, viewMonth, 1);
  let start = first.getDay() - 1;
  if (start < 0) start = 6;
  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
  const prevDays = new Date(viewYear, viewMonth, 0).getDate();
  const today = iso(new Date());
  const grid = document.getElementById("grid");
  grid.innerHTML = "";
  const total = 42;
  for (let i = 0; i < total; i++) {
    let dayNum, cellDate, other = false;
    if (i < start) {
      dayNum = prevDays - start + i + 1;
      cellDate = new Date(viewYear, viewMonth - 1, dayNum);
      other = true;
    } else if (i >= start + daysInMonth) {
      dayNum = i - start - daysInMonth + 1;
      cellDate = new Date(viewYear, viewMonth + 1, dayNum);
      other = true;
    } else {
      dayNum = i - start + 1;
      cellDate = new Date(viewYear, viewMonth, dayNum);
    }
    const ds = iso(cellDate);
    const dayEvents = events.filter(e => e.start === ds).slice(0, 3);
    const more = events.filter(e => e.start === ds).length - 3;
    const el = document.createElement("div");
    el.className = "day" + (other ? " other" : "") + (ds === today ? " today" : "") + (ds === selectedDate ? " selected" : "");
    el.innerHTML = `<div class="day-num">${dayNum}</div>` +
      dayEvents.map(e => `<div class="pill" data-id="${e.id}" style="background:${e.color}">${e.time ? e.time + " " : ""}${e.title}</div>`).join("") +
      (more > 0 ? `<div class="more">+${more} ещё</div>` : "");
    el.onclick = ev => {
      if (ev.target.classList.contains("pill")) {
        openDetail(ev.target.dataset.id);
        ev.stopPropagation();
        return;
      }
      selectedDate = ds;
      document.querySelector("#eventForm [name=date]").value = ds;
      render();
    };
    grid.appendChild(el);
    el.querySelectorAll(".pill").forEach(p => {
      p.onclick = e => { e.stopPropagation(); openDetail(p.dataset.id); };
    });
  }
}

function addMsg(role, text) {
  const c = document.getElementById("chat");
  const d = document.createElement("div");
  d.className = "msg " + role;
  d.textContent = text;
  c.appendChild(d);
  c.scrollTop = c.scrollHeight;
  return d;
}

async function sendChat(e) {
  e.preventDefault();
  const input = document.getElementById("chatInput");
  const text = input.value.trim();
  if (!text) return;
  addMsg("user", text);
  input.value = "";
  const thinking = addMsg("bot thinking", "Думаю…");
  const r = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: text })
  });
  const data = await r.json();
  thinking.remove();
  addMsg("bot", data.reply);
  if (data.event) {
    events.push(data.event);
    selectedDate = data.event.start;
    render();
    setTimeout(() => openDetail(data.event.id), 400);
  }
}

function openModal() {
  document.getElementById("overlay").classList.add("show");
  document.getElementById("modal").classList.add("show");
  document.querySelector("#eventForm [name=date]").value = selectedDate;
}

function closeModal() {
  document.getElementById("modal").classList.remove("show");
  if (!document.getElementById("detailPanel").classList.contains("open"))
    document.getElementById("overlay").classList.remove("show");
}

async function saveManualEvent(e) {
  e.preventDefault();
  const f = e.target;
  const body = {
    title: f.title.value,
    start: f.date.value,
    time: f.time.value,
    location: f.location.value,
    description: f.description.value
  };
  const r = await fetch("/api/events", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const ev = await r.json();
  events.push(ev);
  closeModal();
  f.reset();
  f.date.value = selectedDate;
  render();
  openDetail(ev.id);
}

function openDetail(id) {
  const ev = events.find(x => x.id === id);
  if (!ev) return;
  selectedEventId = id;
  document.getElementById("detailTitle").textContent = ev.title;
  const when = ev.start.split("-").reverse().join(".") + (ev.time ? " · " + ev.time : " · весь день");
  document.getElementById("detailBody").innerHTML =
    `<dt>Когда</dt><dd>${when}</dd>` +
    `<dt>Длительность</dt><dd>${ev.duration_min} мин</dd>` +
    (ev.location ? `<dt>Место</dt><dd>${ev.location}</dd>` : "") +
    (ev.description ? `<dt>Описание</dt><dd>${ev.description}</dd>` : "");
  document.getElementById("overlay").classList.add("show");
  document.getElementById("detailPanel").classList.add("open");
}

function closeDetail() {
  document.getElementById("detailPanel").classList.remove("open");
  document.getElementById("overlay").classList.remove("show");
  selectedEventId = null;
}

async function deleteSelected() {
  if (!selectedEventId) return;
  await fetch("/api/events/" + selectedEventId, { method: "DELETE" });
  events = events.filter(e => e.id !== selectedEventId);
  closeDetail();
  render();
}

init();
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/events", methods=["GET"])
def list_events():
    return jsonify([e.to_dict() for e in STATE.events])


@app.route("/api/events", methods=["POST"])
def create_event():
    data = request.get_json(force=True) or {}
    ev = CalendarEvent(
        id=str(uuid.uuid4())[:8],
        title=(data.get("title") or "Без названия").strip(),
        start=data.get("start") or date.today().isoformat(),
        end=data.get("start") or date.today().isoformat(),
        time=data.get("time") or "",
        duration_min=int(data.get("duration_min") or 60),
        location=(data.get("location") or "").strip(),
        description=(data.get("description") or "").strip(),
        color=COLORS[len(STATE.events) % len(COLORS)],
    )
    STATE.events.append(ev)
    return jsonify(ev.to_dict())


@app.route("/api/events/<event_id>", methods=["DELETE"])
def delete_event(event_id: str):
    STATE.events = [e for e in STATE.events if e.id != event_id]
    return jsonify({"ok": True})


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True) or {}
    message = (data.get("message") or "").strip()
    reply, ev = ai_parse_message(message)
    payload: dict[str, Any] = {"reply": reply, "event": None}
    if ev:
        STATE.events.append(ev)
        payload["event"] = ev.to_dict()
    return jsonify(payload)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ChronoMind — демо календаря с ИИ")
    p.add_argument("--port", type=int, default=5000)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--no-browser", action="store_true", help="Не открывать браузер")
    return p


def main() -> None:
    args = build_parser().parse_args()
    url = f"http://{args.host}:{args.port}"

    if not args.no_browser:
        Timer(1.2, lambda: webbrowser.open(url)).start()

    print(f"ChronoMind запущен: {url}")
    print("Остановка: Ctrl+C")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
