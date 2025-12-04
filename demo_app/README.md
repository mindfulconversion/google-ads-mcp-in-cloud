# AdCortex Google Ads MCP Demo

This demo Flask app spawns the official [google-ads-mcp](https://github.com/googleads/google-ads-mcp) server as a subprocess via stdio, calls the `list_accessible_customers` MCP tool, and renders the returned accounts in a neon "AdCortex" interface.

## Prerequisites

- Python 3.10+
- [pipx](https://pipx.pypa.io/stable/) available on the PATH (used to launch the MCP server)
- Google Ads credentials available as environment variables

### Required environment variables

| Variable | Purpose |
| --- | --- |
| `GOOGLE_ADS_DEVELOPER_TOKEN` | Your Google Ads developer token |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to the ADC JSON credential file (recommended) |
| `GOOGLE_PROJECT_ID` | Project ID housing the Ads API setup |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | Manager login customer ID, if applicable |
| `GOOGLE_ADS_CONFIGURATION_FILE_PATH` | Optional: path to `google-ads.yaml` if you prefer the client library config |
| `FLASK_SECRET_KEY` | Secret key for the Flask session (set to a strong random value in production) |

You can override the subprocess command if needed:

- `MCP_SERVER_COMMAND` (default `pipx`)
- `MCP_SERVER_ARGS` (default `run --spec git+https://github.com/googleads/google-ads-mcp.git google-ads-mcp`)

## Running locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r demo_app/requirements.txt
export GOOGLE_ADS_DEVELOPER_TOKEN=... # and the other vars above
python -m demo_app.app
```

Navigate to http://localhost:8080 and enter the passphrase `mc`, then click **Summon MCP + Fetch Customers** to trigger the subprocess + MCP call.

## How it works

- `demo_app/mcp_client.py` uses the MCP Python client to spawn the server over stdio (`pipx run --spec ... google-ads-mcp`), initializes the session, and calls `list_accessible_customers` with timeouts and structured-content parsing.
- `demo_app/app.py` wires a simple Flask route that requires a passphrase and runs the helper on demand.
- `demo_app/templates/index.html` and `demo_app/static/styles.css` render the AdCortex UI with animated gradients and tiles for each accessible customer.

## Deploying to Azure App Service

1. Provision an App Service with Python 3.10+ and enable SSH/log streaming.
2. Set the environment variables from the table above as Application Settings (include `FLASK_SECRET_KEY`).
3. Deploy the code (e.g., via `git push` or CI) and install the demo requirements during startup:
   ```bash
   pip install -r demo_app/requirements.txt
   ```
4. Configure the startup command, for example:
   ```bash
   gunicorn --bind=0.0.0.0:${PORT:-8000} demo_app.app:create_app()
   ```

The subprocess logs from the MCP server will surface in App Service log streams, making it easier to verify connectivity.

## Extending

To add more MCP tools (e.g., GAQL `search`), create additional helpers in `demo_app/mcp_client.py` that call `session.call_tool("search", {...})` and wire new Flask routes or buttons to trigger them. The existing stdio + timeout handling can be reused for each tool.
