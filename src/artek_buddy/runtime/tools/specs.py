from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    lead_only: bool = False


TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="send_message",
        description=(
            "Post a message to the user in this chat immediately. "
            "Use this whenever you have an update, explanation, intermediate result, "
            "or decision point as soon as it is ready. "
            "Do not tell the user to press Allow — the consent card in the thread is that UI."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Message text to send to the user (supports markdown).",
                },
                "options": {
                    "type": "array",
                    "description": "Optional multiple choice option buttons for the user to pick from.",
                    "items": {"type": "string"},
                },
            },
            "required": ["text"],
        },
    ),
    ToolSpec(
        name="send_file",
        description=(
            "Attach a file to this chat so the owner can download it. "
            "Use a path under this computer's home (or workspace), or pass content "
            "plus a name for a generated file. Do not only mention the path."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File under this bot's home or workspace, e.g. notes.txt or Downloads/report.pdf",
                },
                "name": {
                    "type": "string",
                    "description": "Download filename if different from the path.",
                },
                "content": {
                    "type": "string",
                    "description": "Optional text to write first, then attach (max 1 MB).",
                },
                "text": {
                    "type": "string",
                    "description": "Optional caption shown above the file card.",
                },
            },
        },
    ),
    ToolSpec(
        name="ask_user",
        description=(
            "Ask the user a question with interactive multiple choice buttons. "
            "The user will be able to click an option to reply immediately."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask.",
                },
                "detail": {
                    "type": "string",
                    "description": "Optional description or context under the question.",
                },
                "options": {
                    "type": "array",
                    "description": "List of choice options (e.g. ['A — option 1', 'B — option 2']).",
                    "items": {"type": "string"},
                },
            },
            "required": ["question", "options"],
        },
    ),
    ToolSpec(
        name="remember",
        description=(
            "Write or revise a section of the durable book for this owner or this chat. "
            "Call this when the user states a preference, rule, person, path, machine, "
            "project, or correction. Default scope is the shared owner book. "
            "Use scope=bot for standing rules of this chat (bans, wait for go-ahead). "
            "Call once per fact. A standing rule is this-chat only, not also shared. "
            "Do not store one-off tasks such as opening a tab. "
            "A later note on the same section revises that section; other sections stay. "
            "To erase something, set forget=true with the text to drop."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Fact or rule to write into a book section, or the text to forget.",
                },
                "kind": {
                    "type": "string",
                    "description": (
                        "preference, choice, rule, person, project, place, "
                        "desktop, correction, or workflow."
                    ),
                },
                "scope": {
                    "type": "string",
                    "description": "user (shared, default) or bot (this chat only).",
                },
                "section": {
                    "type": "string",
                    "description": (
                        "Book section to revise: identity, tone, contacts, machines, paths, "
                        "purpose, bans, do_not, wait."
                    ),
                },
                "slot": {
                    "type": "string",
                    "description": "Deprecated alias of section.",
                },
                "forget": {
                    "type": "boolean",
                    "description": "If true, delete matching saved notes instead of adding one.",
                },
                "path": {
                    "type": "string",
                    "description": "Optional document path. Leave empty to append a unique entry.",
                },
            },
            "required": ["content"],
        },
    ),
    ToolSpec(
        name="install_book",
        description=(
            "Install a published skill for this chat from a public http(s) URL. "
            "The stored body is the fetched markdown, not a summary. "
            "Use this when the owner asks to find and keep a skill. "
            "Do not wait for them to dictate the steps. "
            "Not a memory fact and not a cron routine."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Public http(s) URL of the skill markdown.",
                },
            },
            "required": ["url"],
        },
    ),
    ToolSpec(
        name="save_book",
        description=(
            "Revise a skill already kept for this chat. "
            "Do not use this to add a new skill; call install_book with the document URL. "
            "Not a memory fact and not a cron routine. "
            "name is how they will ask for it. when_to_use is the trigger. "
            "body is the steps."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Short name the owner will say later, e.g. Invoice.",
                },
                "when_to_use": {
                    "type": "string",
                    "description": "When to open this book, in one line.",
                },
                "body": {
                    "type": "string",
                    "description": "The steps to follow when this book is opened.",
                },
            },
            "required": ["name", "when_to_use", "body"],
        },
    ),
    ToolSpec(
        name="open_book",
        description=(
            "Load a saved playbook's steps into this turn. "
            "Call this before following those steps. Names are in <skill_books>."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Exact book name or the same words the owner used.",
                }
            },
            "required": ["name"],
        },
    ),
    ToolSpec(
        name="list_apps",
        description=(
            "Search host catalog apps (GitHub, Mail, Docs, and others). "
            "Returns slug, name, and whether it is already connected. "
            "Call this when the owner asks to connect or use an app that is not "
            "already a tool this turn. Then connect_app(slug). "
            "Do not set up git or SSH on this computer for a catalog app."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "q": {
                    "type": "string",
                    "description": "Search text, e.g. github or mail.",
                },
            },
        },
        lead_only=True,
    ),
    ToolSpec(
        name="connect_app",
        description=(
            "Attach a catalog app to this host so its tools load on the next turn. "
            "Pass the slug from list_apps. No-auth apps connect immediately. "
            "Apps that need a login put a card with a URL the owner opens "
            "(not the bot desktop). Do not mint tokens on this machine."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "Catalog slug from list_apps, e.g. github or docs.",
                },
            },
            "required": ["slug"],
        },
        lead_only=True,
    ),
    ToolSpec(
        name="forget_book",
        description="Delete a saved playbook from this chat.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Book name to drop.",
                }
            },
            "required": ["name"],
        },
    ),
    ToolSpec(
        name="read_owner_file",
        description=(
            "Read a file from the owner's paired computer through the desktop client. "
            "Does not ask permission. Without a paired window this fails."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or ~ path on the owner's computer.",
                }
            },
            "required": ["path"],
        },
    ),
    ToolSpec(
        name="write_owner_file",
        description=(
            "Create or overwrite a file on the owner's paired computer. "
            "Asks Allow once / Always / Deny once for writes on that PC. Path stays under the owner's home."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or ~ path on the owner's computer.",
                },
                "content": {
                    "type": "string",
                    "description": "File text to write.",
                },
            },
            "required": ["path", "content"],
        },
    ),
    ToolSpec(
        name="list_owner_dir",
        description=(
            "List a directory on the owner's paired computer. "
            "Does not ask permission. Without a paired window this fails. "
            "On a Russian desktop ~/Downloads is often ~/Загрузки. This Pi's files are under cwd."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or ~ directory on the owner's computer. Default is the home.",
                }
            },
        },
    ),
    ToolSpec(
        name="run_owner_command",
        description=(
            "Run a shell command on the owner's paired computer, like an SSH session. "
            "Batch related small remote checks into one command and one SSH session instead of "
            "calling this tool once per check. "
            "Read-only commands (ls, cat, echo, pwd, uname, …) run without a card. "
            "Commands that can change the PC ask Allow once / Always / Deny once for that bot. "
            "cwd stays under the owner's home. Never copy private keys or edit ~/.ssh/config. "
            "Without a paired window this fails."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to run as the owner.",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory. Default is the owner's home.",
                },
            },
            "required": ["command"],
        },
    ),
    ToolSpec(
        name="open_path",
        description=(
            "Open a URL or workspace file on this bot's Pi desktop. "
            "Opening a website asks the owner Allow once / Always / Deny first."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "URL (http/https) or file path to open on screen.",
                }
            },
            "required": ["path"],
        },
    ),
    ToolSpec(
        name="launch_app",
        description=(
            "Launch an installed graphical application on this bot's desktop "
            "(e.g. 'chromium', 'files', 'terminal'), optionally with a URI/URL. "
            "'files' opens the home folder in the file manager."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "application": {
                    "type": "string",
                    "description": "Application name or binary to launch (chromium, files, terminal).",
                },
                "uri": {
                    "type": "string",
                    "description": "Optional URI or URL to open with the application.",
                },
            },
            "required": ["application"],
        },
    ),
    ToolSpec(
        name="close_app",
        description=(
            "Close a graphical application on this bot's desktop immediately "
            "(e.g. 'chromium' / 'browser' to close the on-screen Chromium). "
            "Use this instead of clicking the window close button."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "application": {
                    "type": "string",
                    "description": "Application name to close (chromium, browser, or a binary name).",
                },
            },
            "required": ["application"],
        },
    ),
    ToolSpec(
        name="computer_observe",
        description=(
            "Look at this bot's Linux desktop: geometry, cursor, and the active window title. "
            "Default is slim (no screenshot). Set include_image only when the title cannot answer "
            "(captcha, canvas, unlabeled buttons). Prefer DOM / curl after the owner allowed the site."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "include_image": {
                    "type": "boolean",
                    "description": "Attach a typed screenshot only when pixels are required.",
                },
            },
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="computer_act",
        description=(
            "Send mouse, keyboard, or launch actions to this bot's Linux desktop. "
            "Opening a site, clicking, typing, or filling a form asks Allow once / Always / Deny first. "
            "Pass several actions in one call. Set return_observe to get a slim observe after the last action."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "actions": {
                    "type": "array",
                    "description": "Ordered desktop actions (click, move, type, key, scroll, wait, open, launch, close).",
                    "items": {"type": "object"},
                },
                "return_observe": {
                    "type": "boolean",
                    "description": "After the actions, return a slim observe (title/geometry, image only if the title is generic).",
                },
            },
            "required": ["actions"],
        },
    ),
    ToolSpec(
        name="browser_act",
        description=(
            "Drive the remote Chromium: open a URL, fill a field, click, type, or submit. "
            "Use this for forms and page actions. The owner must Allow once / Always / Deny first. "
            "Do not use Playwright or CDP to skip this card."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "origin": {
                    "type": "string",
                    "description": "Site origin if already known, e.g. https://example.com",
                },
                "actions": {
                    "type": "array",
                    "description": (
                        "Ordered page actions: goto (url), fill (selector, text), "
                        "click (selector), type (text), press (key), submit (selector?)."
                    ),
                    "items": {"type": "object"},
                },
            },
            "required": ["actions"],
        },
    ),
    ToolSpec(
        name="request_takeover",
        description=(
            "Pause this turn and ask the human to take control of this bot's desktop "
            "(login, captcha, or any page you cannot complete). Pass a short reason. "
            "Do not invent a password. Do not keep calling tools after this."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "What the owner should do in the browser, then Release.",
                },
            },
            "additionalProperties": False,
        },
        lead_only=True,
    ),
    ToolSpec(
        name="message_bot",
        description=(
            "Ask another inbox bot something by exact name or id. This chat shows that "
            "you asked and the question. They work in their own chat. Their last "
            "message comes back here so you can answer the owner. Do not paste their "
            "thread. Do not use this for a worker in this chat (that is spawn_subagent)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "bot": {
                    "type": "string",
                    "description": "Exact inbox name or bot id.",
                },
                "text": {
                    "type": "string",
                    "description": "The question or task for that bot.",
                },
            },
            "required": ["bot", "text"],
        },
        lead_only=True,
    ),
    ToolSpec(
        name="spawn_subagent",
        description="Start a worker on this chat's desktop for one task. Returns immediately with an index.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Short worker name."},
                "task": {"type": "string", "description": "What the worker should do."},
            },
            "required": ["task"],
        },
        lead_only=True,
    ),
    ToolSpec(
        name="list_subagents",
        description="List this chat's workers and their status.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        lead_only=True,
    ),
    ToolSpec(
        name="inspect_subagent",
        description="Read a worker's reasoning, stage, and result. ref is the index, name, or id.",
        input_schema={
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "Subagent index (2), name, or id.",
                }
            },
            "required": ["ref"],
        },
        lead_only=True,
    ),
    ToolSpec(
        name="stop_subagent",
        description="Stop a running worker.",
        input_schema={
            "type": "object",
            "properties": {"ref": {"type": "string"}},
            "required": ["ref"],
        },
        lead_only=True,
    ),
    ToolSpec(
        name="restart_subagent",
        description="Stop a worker if needed and run the same task again.",
        input_schema={
            "type": "object",
            "properties": {"ref": {"type": "string"}},
            "required": ["ref"],
        },
        lead_only=True,
    ),
    ToolSpec(
        name="steer_subagent",
        description=(
            "Give a worker extra instructions while it works. "
            "ref is the index, name, or id. The worker continues the same task."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "Subagent index (2), name, or id.",
                },
                "text": {
                    "type": "string",
                    "description": "The correction or extra instruction.",
                },
            },
            "required": ["ref", "text"],
        },
        lead_only=True,
    ),
)
