"""Utilities for spawning and calling the Google Ads MCP server via stdio."""

import asyncio
import logging
import os
import sys
from datetime import timedelta
from typing import Any, Dict, List

import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import (
    StdioServerParameters,
    get_default_environment,
    stdio_client,
)

# Ensure .env from project root is loaded when running outside Flask entrypoint
try:
    from pathlib import Path
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=False)
except Exception:
    pass

logger = logging.getLogger(__name__)


DEFAULT_COMMAND = "pipx"
DEFAULT_ARGS = [
    "run",
    "--spec",
    "git+https://github.com/googleads/google-ads-mcp.git",
    "google-ads-mcp",
]

GOOGLE_ADS_ENV_KEYS = [
    "GOOGLE_ADS_DEVELOPER_TOKEN",
    "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_PROJECT_ID",
    "GOOGLE_ADS_CONFIGURATION_FILE_PATH",
]


class McpClientError(Exception):
    """Base exception for MCP client errors."""


async def _list_accessible_customers_async(timeout_seconds: int = 45) -> List[Dict[str, Any]]:
    # Choose defaults based on whether local ads_mcp is importable
    use_local_ads_mcp = False
    try:
        import ads_mcp.server  # noqa: F401
        use_local_ads_mcp = True
    except Exception:
        use_local_ads_mcp = False

    default_command = sys.executable if use_local_ads_mcp else DEFAULT_COMMAND
    default_args = ["-m", "ads_mcp.server"] if use_local_ads_mcp else DEFAULT_ARGS

    server_command = os.getenv("MCP_SERVER_COMMAND") or default_command
    if server_command.lower() in ("python", "python.exe"):
        server_command = sys.executable
    server_args_env = os.getenv("MCP_SERVER_ARGS")
    server_args = server_args_env.split(" ") if server_args_env else default_args

    env = get_default_environment()

    # Resolve relative credential/config paths against the repo root so it works no matter the CWD
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    for key in GOOGLE_ADS_ENV_KEYS:
        value = os.environ.get(key)
        if value:
            # Normalize credential/config paths to absolute paths for the subprocess
            if key in ("GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_ADS_CONFIGURATION_FILE_PATH") and not os.path.isabs(value):
                value = os.path.abspath(os.path.join(repo_root, value))
            env[key] = value

    # Validate required auth/config before spawning the subprocess for clearer errors
    if "GOOGLE_ADS_DEVELOPER_TOKEN" not in env:
        raise McpClientError("Missing GOOGLE_ADS_DEVELOPER_TOKEN in environment")

    creds_path = env.get("GOOGLE_APPLICATION_CREDENTIALS")
    if creds_path and not os.path.isfile(creds_path):
        raise McpClientError(f"Credentials file not found at: {creds_path}")

    yaml_cfg = env.get("GOOGLE_ADS_CONFIGURATION_FILE_PATH")
    if yaml_cfg and not os.path.isfile(yaml_cfg):
        raise McpClientError(f"google-ads.yaml not found at: {yaml_cfg}")

    # Map GOOGLE_PROJECT_ID to GOOGLE_CLOUD_PROJECT/GCP_PROJECT for Google auth noise-free defaults
    project = env.get("GOOGLE_PROJECT_ID")
    if project and not env.get("GOOGLE_CLOUD_PROJECT"):
        env["GOOGLE_CLOUD_PROJECT"] = project
    if project and not env.get("GCP_PROJECT"):
        env["GCP_PROJECT"] = project

    # Ensure child process can import local ads_mcp when running from demo_app
    try:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        existing_py_path = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            repo_root if not existing_py_path else repo_root + os.pathsep + existing_py_path
        )
    except Exception:
        # Non-fatal: fallback to whatever PYTHONPATH is set to
        pass

    server_params = StdioServerParameters(
        command=server_command,
        args=server_args,
        env=env,
    )

    try:
        with anyio.fail_after(timeout_seconds):
            async with stdio_client(server_params) as (read_stream, write_stream):
                async with ClientSession(
                    read_stream,
                    write_stream,
                    read_timeout_seconds=timedelta(seconds=timeout_seconds),
                ) as session:
                    await session.initialize()

                    result = await session.call_tool(
                        "list_accessible_customers",
                        read_timeout_seconds=timedelta(seconds=max(5, timeout_seconds - 5)),
                    )

                    return _parse_customers(result)
    except TimeoutError as exc:
        raise McpClientError("Timed out waiting for MCP server response") from exc
    except Exception as exc:  # pragma: no cover - passthrough for runtime issues
        logger.exception("Unexpected MCP client failure")
        raise McpClientError(str(exc)) from exc


def _parse_customers(result: Any) -> List[Dict[str, Any]]:
    customers: List[Dict[str, Any]] = []

    if getattr(result, "structuredContent", None):
        content = result.structuredContent
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    customers.append(
                        {
                            "id": item.get("id") or item.get("customer_id") or item,
                            "name": item.get("name") or item.get("description"),
                        }
                    )
                else:
                    customers.append({"id": item, "name": None})
            return customers

    if getattr(result, "content", None):
        for block in result.content:
            text = getattr(block, "text", None)
            if not text:
                continue
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                # Detect tool/server error messages and surface them as an exception instead of fake customers
                lower = line.lower()
                if (
                    lower.startswith("error executing tool")
                    or "reauthentication is needed" in lower
                    or "unhandled errors in a taskgroup" in lower
                    or "error" in lower
                    or "exception" in lower
                ):
                    logger.error("MCP server error: %s", line)
                    raise McpClientError(line)
                customers.append({"id": line, "name": None})

    if not customers:
        customers.append({"id": "<no results>", "name": None})

    return customers


def list_accessible_customers(timeout_seconds: int = 45) -> List[Dict[str, Any]]:
    """Synchronous wrapper to fetch customers for Flask views."""

    def runner() -> List[Dict[str, Any]]:
        return asyncio.run(_list_accessible_customers_async(timeout_seconds))

    return runner()
