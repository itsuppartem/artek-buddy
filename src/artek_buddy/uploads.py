from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

from artek_buddy.db.shaping import new_id

MAX_UPLOAD_FILES = 10
MAX_UPLOAD_FILE_BYTES = 25 * 1024 * 1024
MAX_UPLOAD_TOTAL_BYTES = 50 * 1024 * 1024
MAX_EXCERPT_BYTES = 32 * 1024
TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".log",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".env",
    ".xml",
    ".html",
    ".css",
    ".sh",
    ".rs",
    ".go",
    ".sql",
}


class UploadError(ValueError):
    """Owner file did not pass ingress checks."""


def safe_filename(name: str) -> str:
    base = Path(str(name or "").strip()).name.replace("\x00", "").strip()
    return (base or "file")[:200]


def guess_mime(name: str, hinted: str | None = None) -> str:
    hinted = (hinted or "").strip().lower()
    if hinted and hinted != "application/octet-stream":
        return hinted
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def unique_inbox_path(inbox: Path, name: str) -> Path:
    safe = safe_filename(name)
    dest = inbox / safe
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    for index in range(2, 1000):
        cand = inbox / f"{stem}-{index}{suffix}"
        if not cand.exists():
            return cand
    return inbox / f"{stem}-{new_id('f')}{suffix}"


def user_file_blocks(text: str, attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    body = (text or "").strip()
    if body:
        blocks.append({"kind": "text", "text": body})
    for item in attachments:
        blocks.append(
            {
                "kind": "file",
                "artifact_id": str(item.get("id") or item.get("artifact_id") or ""),
                "name": str(item.get("name") or "file"),
                "mime_type": str(item.get("mime_type") or "application/octet-stream"),
                "size": int(item.get("size") or 0),
            }
        )
    return blocks


def preview_for_upload(text: str, attachments: list[dict[str, Any]]) -> str:
    body = (text or "").strip()
    if body:
        return body
    names = [str(item.get("name") or "file") for item in attachments]
    return ", ".join(names) if names else "File"


def _is_text(name: str, mime: str, data: bytes) -> bool:
    if mime.startswith("text/") or mime in {"application/json", "application/xml"}:
        return True
    if Path(name).suffix.lower() in TEXT_SUFFIXES:
        return True
    if not data or b"\x00" in data[:1024]:
        return False
    try:
        data[:512].decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def excerpt_text(name: str, mime: str, data: bytes) -> str | None:
    if len(data) > MAX_EXCERPT_BYTES or not _is_text(name, mime, data):
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


def format_user_turn(text: str, attachments: list[dict[str, Any]]) -> str:
    body = (text or "").strip()
    if not attachments:
        return body
    lines = [
        body,
        "",
        f"The user attached {len(attachments)} file(s) into this computer's home (cwd). "
        "Read them from disk. Do not ask the user to paste the contents again.",
    ]
    for item in attachments:
        path = str(item.get("path") or item.get("name") or "file")
        mime = str(item.get("mime_type") or "application/octet-stream")
        size = int(item.get("size") or 0)
        lines.append(f"- {path} ({mime}, {size} bytes)")
        excerpt = item.get("excerpt")
        if excerpt:
            name = str(item.get("name") or Path(path).name)
            lines.extend(["", f"--- {name} ---", str(excerpt).rstrip(), "---"])
    return "\n".join(lines).strip()


def validate_batch(items: list[dict[str, Any]]) -> None:
    if not items:
        raise UploadError("no files")
    if len(items) > MAX_UPLOAD_FILES:
        raise UploadError(f"at most {MAX_UPLOAD_FILES} files")
    total = 0
    for item in items:
        size = int(item.get("size") or 0)
        if size <= 0:
            raise UploadError("empty file")
        if size > MAX_UPLOAD_FILE_BYTES:
            raise UploadError("file too large")
        total += size
    if total > MAX_UPLOAD_TOTAL_BYTES:
        raise UploadError("attachments are too large together")


def _decode_file(name: str, raw_b64: str, mime: str | None) -> dict[str, Any]:
    filename = safe_filename(name)
    try:
        data = base64.b64decode(raw_b64, validate=False)
    except Exception as exc:
        raise UploadError("invalid content_base64") from exc
    item = {
        "name": filename,
        "mime_type": guess_mime(filename, mime),
        "size": len(data),
        "data": data,
    }
    return item


def place_in_inbox(home: Path, name: str, data: bytes) -> str:
    inbox = home / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    dest = unique_inbox_path(inbox, name)
    dest.write_bytes(data)
    return str(Path("inbox") / dest.name)


def inbox_note_path(data_dir: Path, bot_id: str, artifact_id: str) -> Path:
    return Path(data_dir) / "artifacts" / bot_id / f"{artifact_id}.inbox"


def remember_inbox_copy(data_dir: Path, bot_id: str, artifact_id: str, rel: str) -> None:
    note = inbox_note_path(data_dir, bot_id, artifact_id)
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(f"{rel.strip()}\n", encoding="utf-8")


def inbox_path_under_home(home: Path, rel: str) -> Path | None:
    text = (rel or "").strip().replace("\\", "/").lstrip("/")
    if not text.startswith("inbox/") or any(part in {"", ".", ".."} for part in text.split("/")):
        return None
    root = home.resolve()
    dest = (home / text).resolve()
    inbox = (home / "inbox").resolve()
    try:
        dest.relative_to(inbox)
    except ValueError:
        return None
    if dest == inbox:
        return None
    try:
        dest.relative_to(root)
    except ValueError:
        return None
    return dest


def remove_bot_inbox_copies(
    home: Path,
    data_dir: Path,
    bot_id: str,
    artifacts: list[Any] | None = None,
) -> list[str]:
    """Delete that chat's inbox copies. Leaves the rest of a shared Team home."""
    rels: list[str] = []
    notes = Path(data_dir) / "artifacts" / bot_id
    if notes.is_dir():
        for note in notes.glob("*.inbox"):
            rels.append(note.read_text(encoding="utf-8").strip())
    for item in artifacts or []:
        name = getattr(item, "name", None) if not isinstance(item, dict) else item.get("name")
        size = getattr(item, "size", None) if not isinstance(item, dict) else item.get("size")
        rel = f"inbox/{safe_filename(str(name or ''))}"
        dest = inbox_path_under_home(home, rel)
        if dest is None or not dest.is_file():
            continue
        if size not in (None, "") and dest.stat().st_size != int(size):
            continue
        rels.append(rel)
    removed: list[str] = []
    seen: set[str] = set()
    for rel in rels:
        if not rel or rel in seen:
            continue
        seen.add(rel)
        dest = inbox_path_under_home(home, rel)
        if dest is None or not dest.is_file():
            continue
        dest.unlink()
        removed.append(rel)
    return removed


def _load_existing(store: Any, bot_id: str, artifact_id: str) -> dict[str, Any]:
    found = store.get_artifact(str(artifact_id))
    if found is None:
        raise UploadError("attachment not found")
    artifact, stored = found
    if artifact.bot_id != bot_id:
        raise UploadError("attachment not found")
    path = Path(stored)
    if not path.is_file():
        raise UploadError("attachment not found")
    data = path.read_bytes()
    return {
        "id": artifact.id,
        "name": artifact.name,
        "mime_type": artifact.mime_type,
        "size": artifact.size,
        "data": data,
        "excerpt": excerpt_text(artifact.name, artifact.mime_type, data),
        "stored": str(path),
    }


def ingest_uploads(
    *,
    store: Any,
    home: Path,
    data_dir: Path,
    bot_id: str,
    files: list[Any],
    existing_ids: list[str] | None = None,
    run_id: str | None = None,
    copy_to_inbox: bool = True,
) -> list[dict[str, Any]]:
    incoming: list[dict[str, Any]] = []
    for item in files or []:
        name = getattr(item, "name", None) if not isinstance(item, dict) else item.get("name")
        raw = (
            getattr(item, "content_base64", None)
            if not isinstance(item, dict)
            else item.get("content_base64") or item.get("contentBase64")
        )
        mime = (
            getattr(item, "mime_type", None)
            if not isinstance(item, dict)
            else item.get("mime_type") or item.get("mimeType")
        )
        incoming.append(_decode_file(str(name or ""), str(raw or ""), mime))
    for artifact_id in existing_ids or []:
        incoming.append(_load_existing(store, bot_id, str(artifact_id)))
    validate_batch(incoming)
    home.mkdir(parents=True, exist_ok=True)
    out: list[dict[str, Any]] = []
    for item in incoming:
        artifact_id = str(item.get("id") or new_id("art"))
        if "stored" not in item:
            dest_dir = Path(data_dir) / "artifacts" / bot_id
            dest_dir.mkdir(parents=True, exist_ok=True)
            stored = dest_dir / artifact_id
            stored.write_bytes(item["data"])
            store.save_artifact(
                bot_id=bot_id,
                name=item["name"],
                mime_type=item["mime_type"],
                size=item["size"],
                storage_path=str(stored),
                run_id=run_id,
                artifact_id=artifact_id,
            )
        rel = item["name"]
        if copy_to_inbox:
            rel = place_in_inbox(home, item["name"], item["data"])
            remember_inbox_copy(data_dir, bot_id, artifact_id, rel)
        out.append(
            {
                "id": artifact_id,
                "name": item["name"],
                "mime_type": item["mime_type"],
                "size": item["size"],
                "path": rel,
                "excerpt": excerpt_text(item["name"], item["mime_type"], item["data"]),
            }
        )
    return out
