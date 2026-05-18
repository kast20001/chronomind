"""
ChronoMind — демо календаря с ассистентом.
Запуск: py agent.py  →  http://127.0.0.1:5000
"""

from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path
from threading import Timer

from flask import Flask, send_from_directory

ROOT = Path(__file__).resolve().parent
app = Flask(__name__)


@app.route("/")
def index():
    return send_from_directory(ROOT, "index.html")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="ChronoMind — демо календаря")
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
