"""Flask demo that spawns the Google Ads MCP server and lists customers."""

from __future__ import annotations

import logging
import os
from typing import List

from flask import Flask, redirect, render_template, request, session, url_for

from demo_app.mcp_client import McpClientError, list_accessible_customers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-me")

    @app.route("/", methods=["GET", "POST"])
    def index():
        error = None
        customers: List[dict] | None = None
        action = request.form.get("action") if request.method == "POST" else None

        if request.method == "POST":
            if action == "login":
                password = request.form.get("password", "")
                if password == "mc":
                    session["logged_in"] = True
                else:
                    error = "Wrong passphrase. Try again with the secret word."
            elif action == "logout":
                session.clear()
                return redirect(url_for("index"))
            elif action == "fetch" and session.get("logged_in"):
                try:
                    customers = list_accessible_customers()
                except McpClientError as exc:
                    error = str(exc)
                except Exception as exc:  # pragma: no cover - surface unexpected issues
                    logger.exception("Unexpected error while fetching customers")
                    error = f"Failed to fetch customers: {exc}"

        return render_template(
            "index.html",
            logged_in=session.get("logged_in", False),
            error=error,
            customers=customers,
        )

    return app


if __name__ == "__main__":
    create_app().run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
