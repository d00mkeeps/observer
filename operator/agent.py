import os
import json
import html
import logging
from google import genai
from google.genai import types
from tools_codebase import read_codebase_file, search_codebase, list_project_files, get_codebase_overview
from tools_observability import (
    query_all_errors,
    search_container_logs,
    get_error_frequency,
    get_recent_logs,
    get_system_health,
)
from tools_dev import (
    prepare_dev_workspace,
    write_dev_file,
    run_dev_tests,
    propose_patch,
)

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

CRITICAL BEHAVIOR RULES:
1. COMPLETE ANSWERS ONLY: Never emit intermediate filler like "Let me check the code", "I will look into that", or promise to reply in a future turn. Always execute all necessary tools (reading code, searching logs, inspecting frequency) FIRST, and deliver the complete, final answer with code snippets and facts in the same message.
2. THOROUGH INVESTIGATION: Whenever asked about an error, bug, codebase feature, or system state, review all relevant files and Loki logs using your tools before formulating your conclusion.
3. STRICT PRODUCTION SEPARATION & DEV WORKSPACE:
   - Production repos (/codebases/prod) are STRICTLY READ-ONLY.
   - When asked to implement a bugfix, write code, or test a change, work exclusively in the dev sandbox (/workspace/dev/<project>):
     a. Call `prepare_dev_workspace(project)` to sync the dev workspace.
     b. Call `write_dev_file(project, filepath, content)` to apply the patch/tests.
     c. Call `run_dev_tests(project)` to run the automated test suite.
     d. ONLY if tests pass 100%, call `propose_patch(project, commit_message)` to generate the verified proposal for user approval.
     e. If tests fail or cannot be automated, NEVER propose a push. Report the failure clearly.
4. TELEGRAM HTML FORMATTING: Output MUST use Telegram-compatible HTML tags only:
   - <b>bold</b>, <i>italic</i>, <code>code/identifiers</code>, <pre>code blocks</pre>, <blockquote>quotes</blockquote>.
   - Do NOT use Markdown asterisks (**) or Markdown backticks (```).
5. FIX CLASSIFICATIONS (When proposing fixes):
   - 🟢 Tier 1 (Trivial Patch): 1-5 line fix (e.g. null check, default fallback, env var, typo).
   - 🟡 Tier 2 (Moderate Logic): Localized function fix, edge-case logic change.
   - 🔴 Tier 3 (Architectural Refactor): Schema migrations, queue architecture, breaking API change. Explicitly note that a workstation session is required.
6. MARKET & SCIENTIFIC LITERATURE RESEARCH:
   - When asked to conduct market research or analyze competitors (/research):
     * Use `search_google_web` for live competitor sites, pricing benchmarks, and API architectures.
     * Use `search_app_store_reviews` to pull real customer complaints, 1-star reviews, and feature requests for competitor iOS apps (e.g. Whoop, MyFitnessPal, Hevy).
     * Use `search_arxiv` for deep tech, machine learning, CV pose estimation, and algorithm literature.
     * Use `search_google_books` for authoritative exercise science, clinical textbooks, and physiology manuals.
     * Use `search_google_trends` for consumer search volume trends and rising topics.
   - Structure output into 4 clear sections:
     a. 📊 Market Landscape & Top Competitors (pricing, tech stack, key features).
     b. 💡 User Pain Points & Market Gaps (what users complain about / what competitors miss).
     c. 🛠️ Best-in-Class API & Architecture Patterns.
     d. 🎯 Recommended Strategy for Volcano.
"""


from tools_research import (
    search_google_web,
    search_google_books,
    search_google_trends,
    search_arxiv,
    search_app_store_reviews,
)


def _get_agent_tools():
    return [
        read_codebase_file,
        search_codebase,
        list_project_files,
        get_codebase_overview,
        query_all_errors,
        search_container_logs,
        get_error_frequency,
        get_recent_logs,
        get_system_health,
        search_google_web,
        search_google_books,
        search_google_trends,
        search_arxiv,
        search_app_store_reviews,
        prepare_dev_workspace,
        write_dev_file,
        run_dev_tests,
        propose_patch,
    ]


async def translate_error_to_incident_card(container: str, sample_error: str) -> str:
    """Analyze a container error by inspecting logs, history, and codebase, and return a 5-point Incident Card."""
    client = get_genai_client()
    if not client:
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

Please conduct a full autonomous investigation using your tools:
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
        return _extract_response_text(response) or f"🚨 <b>Error in {container}</b>\n<pre>{html.escape(sample_error[:400])}</pre>"
    except Exception as e:
        log.error("Failed to generate incident card with Gemini: %s", e)
        return (
            f"🚨 <b>Error Detected</b> — <code>{html.escape(container)}</code>\n"
            f"<pre>{html.escape(sample_error[:350])}</pre>\n"
            f"<i>(Incident translation error: {html.escape(str(e))})</i>"
        )


def _extract_response_text(response: any) -> str:
    """Extract and concatenate all text parts from response candidates."""
    if not response or not hasattr(response, "candidates") or not response.candidates:
        return getattr(response, "text", "") or ""

    parts_text = []
    for cand in response.candidates:
        if hasattr(cand, "content") and cand.content and hasattr(cand.content, "parts") and cand.content.parts:
            for part in cand.content.parts:
                if hasattr(part, "text") and part.text:
                    parts_text.append(part.text)

    return "\n".join(parts_text).strip() if parts_text else (getattr(response, "text", "") or "")


from skills import ANTI_RATIONALIZATION_RULES


async def process_telegram_message(
    chat_id: str | int,
    user_text: str,
    user_name: str,
    active_skill: dict | None = None,
) -> str:
    """Handle conversational 2-way queries from Telegram with tool calling and optional skill injection."""
    client = get_genai_client()
    if not client:
        return (
            f"🤖 <b>Volcano Operator</b>\n"
            f"Hello {html.escape(user_name)}! 2-way communication is active, but Gemini credentials are not yet configured in <code>.env</code> on Volcano.\n\n"
            f"Please configure <code>GEMINI_API_KEY</code> or <code>GOOGLE_APPLICATION_CREDENTIALS_JSON</code>."
        )

    chat_key = str(chat_id)
    try:
        # If invoking an active engineering skill, format the turn with strict skill instructions
        turn_prompt = user_text
        if active_skill:
            skill_name = active_skill.get("name", "skill")
            skill_body = active_skill.get("body", "")
            turn_prompt = (
                f"[ACTIVE ENGINEERING SKILL: {skill_name.upper()}]\n"
                f"{skill_body}\n"
                f"{ANTI_RATIONALIZATION_RULES}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"[USER INSTRUCTION]:\n{user_text}\n\n"
                f"Execute the above workflow. If performing TDD (build), prepare the dev workspace, write tests first, run tests, and propose patch only when 100% pass."
            )

        if chat_key not in _active_chats or active_skill is not None:
            _active_chats[chat_key] = client.chats.create(
                model=MODEL_NAME,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    tools=_get_agent_tools(),
                    temperature=0.2,
                ),
            )
        
        chat_session = _active_chats[chat_key]
        response = chat_session.send_message(turn_prompt)
        extracted = _extract_response_text(response)
        
        # If response is empty or model only output an intermediate turn, follow up to get final answer
        if not extracted or extracted.lower().startswith("let me check"):
            follow_up = chat_session.send_message("Please provide your complete, finalized answer based on your tool inspection findings.")
            follow_up_text = _extract_response_text(follow_up)
            if follow_up_text:
                extracted = follow_up_text

        return extracted or "<i>(No response generated)</i>"
    except Exception as e:
        log.error("Error in process_telegram_message: %s", e)
        # Reset chat session on error
        _active_chats.pop(chat_key, None)
        return f"⚠️ <b>Agent Error:</b> {html.escape(str(e))}"
