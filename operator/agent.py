import os
import json
import html
import logging
from google import genai
from google.genai import types
from tools_codebase import read_codebase_file, search_codebase, list_project_files
from tools_observability import get_error_frequency, get_recent_logs, get_system_health

log = logging.getLogger("operator.agent")

MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

_client: genai.Client | None = None
_active_chats: dict[str, any] = {}


def get_genai_client() -> genai.Client | None:
    global _client
    if _client is not None:
        return _client

    # 1. Check for standard Google AI Studio GEMINI_API_KEY
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if api_key:
        try:
            _client = genai.Client(api_key=api_key)
            log.info("Initialized Gemini Client with GEMINI_API_KEY")
            return _client
        except Exception as e:
            log.error("Failed to initialize genai.Client with API key: %s", e)

    # 2. Check for Google Cloud Service Account (Vertex AI / Volc credentials)
    creds_json_raw = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON", "").strip()
    creds_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1").strip()

    if creds_json_raw or creds_file:
        try:
            from google.oauth2 import service_account
            if creds_json_raw:
                info = json.loads(creds_json_raw)
                creds = service_account.Credentials.from_service_account_info(
                    info,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
                if not project_id:
                    project_id = info.get("project_id", "")
            else:
                creds = service_account.Credentials.from_service_account_file(
                    creds_file,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )

            _client = genai.Client(
                vertexai=True,
                project=project_id,
                location=location,
                credentials=creds,
            )
            log.info("Initialized Gemini Client on Vertex AI (project=%s, location=%s)", project_id, location)
            return _client
        except Exception as e:
            log.error("Failed to initialize genai.Client with Vertex AI service account: %s", e)

    log.warning("No valid GEMINI_API_KEY or GOOGLE_APPLICATION_CREDENTIALS found.")
    return None


SYSTEM_INSTRUCTION = """You are Volcano Observer, an autonomous SRE and Codebase Intelligence assistant for the production host 'volcano'.
Your role is to be a clear, human-friendly translator between raw server infrastructure/code and the engineer on their phone.

Capabilities & Guidelines:
1. You have STRICT READ-ONLY access to production codebases and container logs/metrics via your tools.
2. Output formatting MUST use Telegram-compatible HTML tags only:
   - <b>bold</b>, <i>italic</i>, <code>code/identifiers</code>, <pre>code blocks</pre>, <blockquote>quotes</blockquote>.
   - Do NOT use Markdown asterisks or standard markdown backticks.
3. Keep responses concise, direct, and high-signal for quick reading on a mobile device.
4. When investigating errors, classify the fix into one of 3 tiers:
   - 🟢 Tier 1 (Trivial Patch): 1-5 line fix (e.g. null check, default fallback, env var, typo). Ready for one-tap approval once write mode is enabled.
   - 🟡 Tier 2 (Moderate Logic): Localized function fix, edge-case logic change. Requires code review.
   - 🔴 Tier 3 (Architectural Refactor): Schema migrations, queue architecture, breaking API change. State that this requires a workstation session, not suitable for mobile approval.
"""


def _get_agent_tools():
    return [
        read_codebase_file,
        search_codebase,
        list_project_files,
        get_error_frequency,
        get_recent_logs,
        get_system_health,
    ]


async def translate_error_to_incident_card(container: str, sample_error: str) -> str:
    """Analyze a container error by inspecting logs, history, and codebase, and return a 5-point Incident Card."""
    client = get_genai_client()
    if not client:
        # Fallback to structured plain summary if Gemini is not configured
        freq_info = get_error_frequency(container, days=7)
        return (
            f"🚨 <b>App Error</b> — <code>{html.escape(container)}</code>\n"
            f"<pre>{html.escape(sample_error[:350])}</pre>\n"
            f"<b>7-Day Frequency:</b>\n<i>{html.escape(freq_info)}</i>\n"
            f"<i>(Configure Gemini credentials for full AI root-cause analysis & Tier classification)</i>"
        )

    prompt = f"""An error occurred in production container: '{container}'.
Error snippet:
{sample_error}

Please conduct a brief investigation using your tools:
1. Check how frequently errors have occurred for this container in the last 7 days (use `get_error_frequency`).
2. Search and inspect the relevant codebase to find the exact file and lines responsible for this error (use `search_codebase` / `read_codebase_file`).
3. Construct a super short, clean, human-readable Incident Card in Telegram HTML format.

Required Incident Card Structure:
🚨 <b>Incident: [Brief 3-5 word Title]</b>
• <b>App:</b> <code>{container}</code>
• <b>Impact:</b> [Critical / Degraded / Low / Obscure] — [1-sentence plain-English impact]
• <b>7-Day Frequency:</b> [Occurrences count & trend]

🔍 <b>Suspected Cause:</b>
[Exact filename:line and 1-2 sentence human-readable explanation of why it happened]

💡 <b>Proposed Fix ([🟢 Tier 1 / 🟡 Tier 2 / 🔴 Tier 3]):</b>
[Clear, human-readable solution. If Tier 1, include a tiny 2-4 line <pre> diff snippet and note: '(Simple fix. Ready for one-tap approval when write-mode is enabled.)'. If Tier 3, note that workstation refactoring is needed.]
"""

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=_get_agent_tools(),
                temperature=0.2,
            ),
        )
        return response.text or f"🚨 <b>Error in {container}</b>\n<pre>{html.escape(sample_error[:400])}</pre>"
    except Exception as e:
        log.error("Failed to generate incident card with Gemini: %s", e)
        return (
            f"🚨 <b>Error Detected</b> — <code>{html.escape(container)}</code>\n"
            f"<pre>{html.escape(sample_error[:350])}</pre>\n"
            f"<i>(Incident translation error: {html.escape(str(e))})</i>"
        )


async def process_telegram_message(chat_id: str | int, user_text: str, user_name: str) -> str:
    """Handle conversational 2-way queries from Telegram with tool calling and history."""
    client = get_genai_client()
    if not client:
        return (
            f"🤖 <b>Volcano Operator</b>\n"
            f"Hello {html.escape(user_name)}! 2-way communication is active, but Gemini credentials are not yet configured in <code>.env</code> on Volcano.\n\n"
            f"Please configure <code>GEMINI_API_KEY</code> or <code>GOOGLE_APPLICATION_CREDENTIALS_JSON</code>."
        )

    chat_key = str(chat_id)
    try:
        if chat_key not in _active_chats:
            _active_chats[chat_key] = client.chats.create(
                model=MODEL_NAME,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    tools=_get_agent_tools(),
                    temperature=0.3,
                ),
            )
        
        chat_session = _active_chats[chat_key]
        response = chat_session.send_message(user_text)
        return response.text or "<i>(No response generated)</i>"
    except Exception as e:
        log.error("Error in process_telegram_message: %s", e)
        # Reset chat session on error
        _active_chats.pop(chat_key, None)
        return f"⚠️ <b>Agent Error:</b> {html.escape(str(e))}"
