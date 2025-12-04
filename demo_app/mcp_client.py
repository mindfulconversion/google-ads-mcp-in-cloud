"""Utilities for spawning and calling the Google Ads MCP server via stdio."""

import asyncio
import logging
import os
from datetime import timedelta
from typing import Any, Dict, List

import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import (
    StdioServerParameters,
    get_default_environment,
    stdio_client,
)

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
    server_command = os.getenv("MCP_SERVER_COMMAND", DEFAULT_COMMAND)
    server_args_env = os.getenv("MCP_SERVER_ARGS")
    server_args = server_args_env.split(" ") if server_args_env else DEFAULT_ARGS

    env = get_default_environment()
    for key in GOOGLE_ADS_ENV_KEYS:
        value = os.environ.get(key)
        if value:
            env[key] = value

    if "GOOGLE_ADS_DEVELOPER_TOKEN" not in env:
        raise McpClientError("Missing GOOGLE_ADS_DEVELOPER_TOKEN in environment")

    server_params = StdioServerParameters(
        command=server_command,
        args=server_args,
        env=env,
    )

    try:
        async with anyio.fail_after(timeout_seconds):
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
                customers.append({"id": line, "name": None})

    if not customers:
        customers.append({"id": "<no results>", "name": None})

    return customers


def list_accessible_customers(timeout_seconds: int = 45) -> List[Dict[str, Any]]:
    """Synchronous wrapper to fetch customers for Flask views."""

    def runner() -> List[Dict[str, Any]]:
        return asyncio.run(_list_accessible_customers_async(timeout_seconds))

    return runner()
