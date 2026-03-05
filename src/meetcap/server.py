"""Flask web server for browsing processed recordings and tracking action items."""
from __future__ import annotations

import calendar
import threading
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional

from flask import Flask, redirect, render_template, request, url_for
from werkzeug.serving import make_server

from .actions import (
    close_item,
    get_all_items,
    get_items_for_stem,
    get_open_count,
    init_db,
    reopen_item,
    sync_from_markdown,
)
from .config import get_output_dir
from .processor import parse_filename_datetime

PORT = 5420

_server = None
_thread = None


def _format_stem(stem: str) -> str:
    """Format a recording stem as a human-readable date/time string."""
    try:
        dt = parse_filename_datetime(stem + ".wav")
        return dt.strftime("%B %d, %Y at %I:%M %p").replace(" 0", " ")
    except Exception:
        return stem


def _month_label(month_key: str) -> str:
    """Convert 'YYYY-MM' to 'Month YYYY'."""
    try:
        year, month = month_key.split("-")
        return f"{calendar.month_name[int(month)]} {year}"
    except Exception:
        return month_key


def _split_markdown(body: str) -> tuple[str, str]:
    """Split markdown into (summary_without_frontmatter, transcript)."""
    separator = "\n---\n\n# Full Transcript\n"
    if separator in body:
        summary_part, transcript_part = body.split(separator, 1)
    else:
        summary_part, transcript_part = body, ""

    # Strip YAML front matter
    lines = summary_part.split("\n")
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                summary_part = "\n".join(lines[i + 1:]).strip()
                break

    return summary_part, transcript_part.strip()


def create_app(config: Dict[str, Any]) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    init_db()

    @app.route("/")
    def index():
        output_dir = get_output_dir(config)
        recordings = []
        if output_dir.exists():
            for md_path in sorted(
                output_dir.glob("**/*.md"),
                key=lambda p: p.stem,
                reverse=True,
            ):
                stem = md_path.stem
                items = get_items_for_stem(stem)
                open_count = sum(1 for i in items if i["status"] == "open")
                recordings.append(
                    {
                        "stem": stem,
                        "formatted": _format_stem(stem),
                        "open_count": open_count,
                    }
                )

        # Group by YYYY-MM
        groups_dict: dict[str, list] = {}
        for r in recordings:
            try:
                dt = parse_filename_datetime(r["stem"] + ".wav")
                key = dt.strftime("%Y-%m")
            except Exception:
                key = "unknown"
            groups_dict.setdefault(key, []).append(r)

        sorted_groups = [
            (key, _month_label(key), recs)
            for key, recs in sorted(groups_dict.items(), reverse=True)
        ]

        return render_template(
            "index.html",
            groups=sorted_groups,
            total_open=get_open_count(),
        )

    @app.route("/recording/<stem>")
    def recording(stem: str):
        output_dir = get_output_dir(config)
        md_path: Optional[Path] = None
        for p in output_dir.glob(f"**/{stem}.md"):
            md_path = p
            break

        if md_path is None or not md_path.exists():
            return "Recording not found", 404

        body = md_path.read_text(encoding="utf-8")
        sync_from_markdown(stem, body)

        summary_text, transcript_text = _split_markdown(body)

        import markdown as md_lib

        summary_html = md_lib.markdown(
            summary_text,
            extensions=["extra", "tables", "fenced_code"],
        )

        items = get_items_for_stem(stem)

        return render_template(
            "recording.html",
            stem=stem,
            formatted=_format_stem(stem),
            summary_html=summary_html,
            transcript=transcript_text,
            items=items,
            total_open=get_open_count(),
        )

    @app.route("/actions")
    def actions():
        items = get_all_items()
        groups_dict: dict[str, list] = {}
        for item in items:
            groups_dict.setdefault(item["stem"], []).append(item)

        formatted_groups = [
            (stem, _format_stem(stem), item_list)
            for stem, item_list in sorted(groups_dict.items(), reverse=True)
        ]

        return render_template(
            "actions.html",
            groups=formatted_groups,
            total_open=get_open_count(),
        )

    @app.route("/actions/<int:item_id>/close", methods=["POST"])
    def close_action(item_id: int):
        close_item(item_id)
        return redirect(request.referrer or url_for("actions"))

    @app.route("/actions/<int:item_id>/reopen", methods=["POST"])
    def reopen_action(item_id: int):
        reopen_item(item_id)
        return redirect(request.referrer or url_for("actions"))

    return app


def start_server(config: Dict[str, Any]) -> str:
    """Start the Werkzeug server in a daemon thread. Returns the base URL."""
    global _server, _thread
    if _server is not None:
        return f"http://127.0.0.1:{PORT}"

    app = create_app(config)
    _server = make_server("127.0.0.1", PORT, app)
    _thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _thread.start()
    return f"http://127.0.0.1:{PORT}"


def stop_server() -> None:
    """Shut down the running server, if any."""
    global _server, _thread
    if _server is not None:
        _server.shutdown()
        _server = None
        _thread = None


def open_recordings(config: Dict[str, Any]) -> None:
    """Start the server (if needed) and open the recordings index in a browser."""
    url = start_server(config)
    webbrowser.open(url)


def open_actions(config: Dict[str, Any]) -> None:
    """Start the server (if needed) and open the action items page in a browser."""
    url = start_server(config)
    webbrowser.open(f"{url}/actions")
