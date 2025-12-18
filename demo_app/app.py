"""Flask demo that spawns the Google Ads MCP server and lists customers."""

from __future__ import annotations

import logging
import os
import sys
from typing import List
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from project root .env
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=False)

from flask import Flask, redirect, render_template, request, session, url_for
try:
    # When executed as a package: python -m demo_app.app (from repo root)
    from demo_app.crew_runner import run_initial_analysis, run_hypothesis
    from demo_app.mcp_client import McpClientError, list_accessible_customers
except ModuleNotFoundError:
    # When executed from inside demo_app directory: python app.py
    from crew_runner import run_initial_analysis, run_hypothesis
    from mcp_client import McpClientError, list_accessible_customers

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Also log everything to a local file for debugging, in case stdout is flaky (e.g., on Windows with reloader)
log_file = Path(__file__).resolve().parent / "demo_app.log"
file_handler = logging.FileHandler(log_file, encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(
    logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s")
)
root_logger = logging.getLogger()
root_logger.addHandler(file_handler)

logger = logging.getLogger(__name__)

# Ensure Werkzeug (Flask dev server) request logs go to our console handler
for _name in ("werkzeug", "werkzeug.serving"):
    _log = logging.getLogger(_name)
    _log.handlers.clear()
    _log.setLevel(logging.INFO)
    _log.propagate = True


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-me")

    @app.before_request
    def _log_request():
        logger.info("Request: %s %s", request.method, request.path)

    @app.route("/", methods=["GET", "POST"])
    def index():
        # Loud debug print to verify stdout reaches the terminal
        print("[DEBUG] Entered index()", file=sys.stdout, flush=True)

        error = None
        status = None
        customers: List[dict] | None = None
        action = request.form.get("action") if request.method == "POST" else None

        if request.method == "POST" and session.get("logged_in"):
            try:
                if action == "fetch":
                    customers = list_accessible_customers()
                elif action == "run_analysis":
                    status = run_initial_analysis()
                elif action == "run_hypothesis":
                    status = run_hypothesis()
            except McpClientError as exc:
                logger.exception("MCP client error while handling action: %s", action)
                error = str(exc)
            except Exception as exc:  # pragma: no cover - surface unexpected issues
                logger.exception("Unexpected error handling action: %s", action)
                error = f"Failed to process action '{action}': {exc}"

        return render_template(
            "index.html",
            logged_in=session.get("logged_in", False),
            error=error,
            status=status,
            customers=customers,
        )

    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = None
        
        # If already logged in, redirect to home
        if session.get("logged_in"):
            return redirect(url_for("index"))
        
        if request.method == "POST":
            password = request.form.get("password", "")
            if password == "mc":
                session["logged_in"] = True
                return redirect(url_for("index"))
            else:
                error = "Invalid passphrase. Please try again."
        
        return render_template("login.html", error=error)

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        return redirect(url_for("index"))

    return app


if __name__ == "__main__":
    # Ensure stdout is line-buffered where supported (helps in some Windows terminals)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    app = create_app()
    app.run(
        debug=False,          # disable debugger to avoid child process swallowing stdout
        use_reloader=False,   # explicitly disable reloader (single-process mode)
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
    )
