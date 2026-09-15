#!/usr/bin/env python3
"""Rename Codex chat titles across the local metadata stores.

This script is intentionally conservative:
- it reads the complete chat list from `state_5.sqlite`
- it updates the SQLite `threads.title` field
- it updates or inserts the matching row in `session_index.jsonl`
- it updates the latest `thread_name_updated` event in the session JSONL,
  or appends one if the session has never been named
- it creates timestamped backups before writing anything
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class ThreadRecord:
    thread_id: str
    display_title: str
    db_title: str
    index_title: str | None
    archived: bool
    updated_at_ms: int
    rollout_path: str


@dataclass
class AuditRecord:
    thread: ThreadRecord
    session_path: Path
    event_title: str | None
    foreign_events: list[tuple[int, str, str | None]]
    problems: list[str]
    canonical_title: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rename a Codex chat title in a copied ~/.codex directory."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Path to the Codex data directory. Defaults to ~/.codex",
    )
    parser.add_argument(
        "--filter",
        default="",
        help="Only show chats whose title or id contains this case-insensitive text.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List matching chats and exit without renaming anything.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of chats to show in the interactive list. Default: 50.",
    )
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="Only show non-archived chats.",
    )
    parser.add_argument(
        "--thread-id",
        default=None,
        help="Rename a specific thread id directly, without choosing by index.",
    )
    parser.add_argument(
        "--new-title",
        default=None,
        help="New title to apply. If omitted, the script will prompt for it.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the final confirmation prompt.",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Audit chat title consistency across SQLite, session_index.jsonl, and session JSONLs.",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Repair chat title drift across metadata stores for the selected chats.",
    )
    parser.add_argument(
        "--prune-foreign-events",
        action="store_true",
        help="When syncing, remove thread_name_updated events in a session file that belong to another thread id.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        root = resolve_root(args.root)
        threads = load_threads(root)
    except Exception as exc:
        target = args.root.expanduser() if args.root is not None else Path(__file__).resolve().parent
        print(f"Error loading Codex data from {target}: {exc}", file=sys.stderr)
        return 1

    if args.active_only:
        threads = [thread for thread in threads if not thread.archived]

    filtered = filter_threads(threads, args.filter)
    if not filtered and not args.thread_id:
        print("No matching chats found.")
        return 1

    if args.audit or args.sync:
        target_threads = threads if args.thread_id else filtered
        try:
            audits = [inspect_thread(root, thread) for thread in target_threads]
        except Exception as exc:
            print(f"Audit failed: {exc}", file=sys.stderr)
            return 1

        if args.audit:
            print_audit(audits)
            return 0

        syncable = [audit for audit in audits if audit.problems]
        if not syncable:
            print("No drift found in the selected chats.")
            return 0

        print_audit(syncable)
        if not args.yes:
            print()
            confirm = input(f"Repair {len(syncable)} chat(s)? [y/N]: ").strip().lower()
            if confirm not in {"y", "yes"}:
                print("Sync cancelled.")
                return 0

        try:
            full_backup_path = prepare_mutation(root)
            backup_dir, changed = sync_audits(
                root,
                syncable,
                prune_foreign_events=args.prune_foreign_events,
            )
        except Exception as exc:
            print(f"Sync failed: {exc}", file=sys.stderr)
            return 1

        print()
        print(f"Repaired {changed} chat(s)")
        print(f"Full backup : {full_backup_path}")
        print(f"Backups: {backup_dir}")
        return 0

    if args.list:
        print_threads(filtered, args.limit)
        return 0

    if args.thread_id is None and args.new_title is None and sys.stdin.isatty():
        return interactive_rename_loop(root, args)

    try:
        selected = choose_thread(threads if args.thread_id else filtered, args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    new_title = get_new_title(selected, args)
    if new_title is None:
        print("Rename cancelled.")
        return 0

    if new_title == selected.display_title:
        print("New title is unchanged. Nothing to do.")
        return 0

    if not confirm_rename(selected, new_title, args):
        print("Rename cancelled.")
        return 0

    try:
        full_backup_path = prepare_mutation(root)
        backup_dir = rename_thread(root, selected, new_title)
    except Exception as exc:
        print(f"Rename failed: {exc}", file=sys.stderr)
        return 1

    print()
    print(f"Renamed thread {selected.thread_id}")
    print(f"New title: {new_title}")
    print(f"Full backup : {full_backup_path}")
    print(f"Backups: {backup_dir}")
    return 0


def resolve_root(explicit_root: Path | None) -> Path:
    if explicit_root is not None:
        root = explicit_root.expanduser().resolve()
    else:
        # Defaults to ~/.codex if --root is not given
        root = Path("~/.codex").expanduser().resolve()
        #root = Path(__file__).resolve().parent

    required = [root / "state_5.sqlite", root / "session_index.jsonl"]
    missing = [path.name for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(
            f"{root} does not look like a Codex data directory; missing: {', '.join(missing)}"
        )
    return root


def filter_threads(threads: list[ThreadRecord], needle: str) -> list[ThreadRecord]:
    needle = needle.strip().lower()
    if not needle:
        return threads
    return [
        thread
        for thread in threads
        if needle in thread.display_title.lower() or needle in thread.thread_id.lower()
    ]


def load_threads(root: Path) -> list[ThreadRecord]:
    index_by_id = load_session_index(root / "session_index.jsonl")
    with sqlite3.connect(root / "state_5.sqlite") as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, title, archived, updated_at, rollout_path
            FROM threads
            ORDER BY updated_at DESC
            """
        ).fetchall()

    threads: list[ThreadRecord] = []
    for row in rows:
        thread_id = str(row["id"])
        db_title = row["title"] or ""
        index_title = index_by_id.get(thread_id, {}).get("thread_name")
        display_title = index_title or db_title or "<untitled>"
        threads.append(
            ThreadRecord(
                thread_id=thread_id,
                display_title=display_title,
                db_title=db_title,
                index_title=index_title,
                archived=bool(row["archived"]),
                updated_at_ms=int(row["updated_at"]),
                rollout_path=str(row["rollout_path"]),
            )
        )
    return threads


def load_session_index(path: Path) -> dict[str, dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            thread_id = item.get("id")
            if thread_id:
                items[str(thread_id)] = item
    return items


def resolve_session_path(root: Path, rollout_path: str, thread_id: str) -> Path:
    raw = Path(rollout_path)
    if not raw.is_absolute():
        candidate = (root / raw).resolve()
        if candidate.exists():
            return candidate

    parts = list(raw.parts)
    if ".codex" in parts:
        suffix = Path(*parts[parts.index(".codex") + 1 :])
        candidate = root / suffix
        if candidate.exists():
            return candidate

    if raw.is_relative_to(root):
        return raw

    search_roots = [root / "sessions", root / "archived_sessions"]
    basename = raw.name
    exact_matches: list[Path] = []
    for search_root in search_roots:
        if search_root.exists():
            exact_matches.extend(search_root.rglob(basename))
    if len(exact_matches) == 1:
        return exact_matches[0]

    id_matches: list[Path] = []
    for search_root in search_roots:
        if search_root.exists():
            id_matches.extend(search_root.rglob(f"*{thread_id}.jsonl"))
    if len(id_matches) == 1:
        return id_matches[0]

    raise FileNotFoundError(
        f"could not resolve session file for thread {thread_id} from {rollout_path}"
    )


def choose_thread(threads: list[ThreadRecord], args: argparse.Namespace) -> ThreadRecord:
    if args.thread_id:
        for thread in threads:
            if thread.thread_id == args.thread_id:
                return thread
        raise ValueError(f"Thread id not found in filtered set: {args.thread_id}")

    print_threads(threads, args.limit)
    raw = input("Pick a chat by index: ").strip()
    if not raw:
        raise ValueError("No index entered.")
    try:
        idx = int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid index: {raw}") from exc
    if idx < 0 or idx >= min(len(threads), args.limit):
        raise ValueError(f"Index out of range: {idx}")
    return threads[idx]


def get_new_title(thread: ThreadRecord, args: argparse.Namespace) -> str | None:
    if args.new_title is not None:
        new_title = args.new_title.strip()
    else:
        print()
        print(f"Current title: {thread.display_title}")
        new_title = input("Enter a new title: ").strip()
    if not new_title:
        return None
    return new_title


def print_threads(threads: list[ThreadRecord], limit: int) -> None:
    limit = max(limit, 1)
    shown = threads[:limit]
    for idx, thread in enumerate(shown):
        updated = format_timestamp_ms(thread.updated_at_ms)
        state = "archived" if thread.archived else "active"
        title = shorten(thread.display_title, 100)
        print(f"[{idx:>2}] {updated}  {state:8}  {title}")
        print(f"     {thread.thread_id}")
    if len(threads) > limit:
        remaining = len(threads) - limit
        print()
        print(f"... {remaining} more match(es). Re-run with --limit {len(threads)} to show all.")


def interactive_rename_loop(root: Path, args: argparse.Namespace) -> int:
    full_backup_path: Path | None = None
    rename_count = 0

    while True:
        try:
            threads = load_threads(root)
        except Exception as exc:
            print(f"Failed to reload chats: {exc}", file=sys.stderr)
            return 1

        if args.active_only:
            threads = [thread for thread in threads if not thread.archived]
        filtered = filter_threads(threads, args.filter)
        if not filtered:
            print("No matching chats found.")
            return 1

        try:
            selected = choose_thread(filtered, args)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        new_title = get_new_title(selected, args)
        if new_title is None:
            print("Rename cancelled.")
        elif new_title == selected.display_title:
            print("New title is unchanged. Nothing to do.")
        else:
            if not confirm_rename(selected, new_title, args):
                print("Rename cancelled.")
            else:
                try:
                    if full_backup_path is None:
                        full_backup_path = prepare_mutation(root)
                    backup_dir = rename_thread(root, selected, new_title)
                except Exception as exc:
                    print(f"Rename failed: {exc}", file=sys.stderr)
                    return 1

                rename_count += 1
                print()
                print(f"Renamed thread {selected.thread_id}")
                print(f"New title   : {new_title}")
                print(f"Full backup : {full_backup_path}")
                print(f"Backups     : {backup_dir}")

        print()
        if not prompt_yes_no("Rename another chat? [y/N]: "):
            break
        print()

    if rename_count == 0:
        print("No chats were renamed.")
    else:
        print(f"Renamed {rename_count} chat(s) in this session.")
        if full_backup_path is not None:
            print(f"Full backup : {full_backup_path}")
    return 0


def confirm_rename(thread: ThreadRecord, new_title: str, args: argparse.Namespace) -> bool:
    if args.yes:
        return True

    print()
    print(f"Thread id : {thread.thread_id}")
    print(f"Old title : {thread.display_title}")
    print(f"New title : {new_title}")
    confirm = input("Apply this rename? [y/N]: ").strip().lower()
    return confirm in {"y", "yes"}


def prompt_yes_no(prompt: str) -> bool:
    answer = input(prompt).strip().lower()
    return answer in {"y", "yes"}


def inspect_thread(root: Path, thread: ThreadRecord) -> AuditRecord:
    session_path = resolve_session_path(root, thread.rollout_path, thread.thread_id)
    event_title: str | None = None
    foreign_events: list[tuple[int, str, str | None]] = []

    with session_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            item = json.loads(line)
            payload = item.get("payload", {})
            if item.get("type") != "event_msg":
                continue
            if payload.get("type") != "thread_name_updated":
                continue
            event_thread_id = payload.get("thread_id")
            if event_thread_id == thread.thread_id:
                event_title = payload.get("thread_name")
            else:
                foreign_events.append(
                    (line_number, str(event_thread_id), payload.get("thread_name"))
                )

    problems: list[str] = []
    if thread.index_title is None:
        problems.append("missing_index")
    if event_title is None:
        problems.append("missing_event")
    if thread.index_title is not None and thread.db_title != thread.index_title:
        problems.append("db_vs_index")
    if event_title is not None and thread.db_title != event_title:
        problems.append("db_vs_event")
    if (
        thread.index_title is not None
        and event_title is not None
        and thread.index_title != event_title
    ):
        problems.append("index_vs_event")
    if foreign_events:
        problems.append("foreign_event_in_file")

    canonical_title = choose_canonical_title(thread.db_title, thread.index_title, event_title)
    return AuditRecord(
        thread=thread,
        session_path=session_path,
        event_title=event_title,
        foreign_events=foreign_events,
        problems=problems,
        canonical_title=canonical_title,
    )


def choose_canonical_title(
    db_title: str, index_title: str | None, event_title: str | None
) -> str:
    if index_title and event_title:
        if index_title == event_title:
            return index_title
        return index_title
    if index_title:
        return index_title
    if event_title:
        return event_title
    return db_title


def print_audit(audits: list[AuditRecord]) -> None:
    total = len(audits)
    drifted = [audit for audit in audits if audit.problems]
    print(f"Audited {total} chat(s); found drift in {len(drifted)}.")
    if not drifted:
        return
    print()
    for audit in drifted:
        thread = audit.thread
        state = "archived" if thread.archived else "active"
        print(f"{thread.thread_id}  {state}  {shorten(thread.display_title, 80)}")
        print(f"  problems : {', '.join(audit.problems)}")
        print(f"  db       : {thread.db_title or '<empty>'}")
        print(f"  index    : {audit.thread.index_title or '<missing>'}")
        print(f"  event    : {audit.event_title or '<missing>'}")
        print(f"  canonical: {audit.canonical_title or '<empty>'}")
        if audit.foreign_events:
            for line_number, foreign_thread_id, foreign_title in audit.foreign_events:
                print(
                    "  foreign  : "
                    f"line {line_number} has thread_id={foreign_thread_id} "
                    f"title={foreign_title or '<empty>'}"
                )
        print(f"  session  : {audit.session_path}")
        print()


def format_timestamp_ms(timestamp_ms: int) -> str:
    dt = datetime.fromtimestamp(timestamp_ms, tz=UTC)
    return dt.strftime("%Y-%m-%d %H:%M")


def shorten(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: width - 3] + "..."


def rename_thread(root: Path, thread: ThreadRecord, new_title: str) -> Path:
    session_path = resolve_session_path(root, thread.rollout_path, thread.thread_id)
    backup_dir = root / ".chat_rename_backups" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_dir.mkdir(parents=True, exist_ok=False)

    backup_file(root / "state_5.sqlite", backup_dir, root)
    for suffix in ("-wal", "-shm"):
        sidecar = root / f"state_5.sqlite{suffix}"
        if sidecar.exists():
            backup_file(sidecar, backup_dir, root)
    backup_file(root / "session_index.jsonl", backup_dir, root)
    backup_file(session_path, backup_dir, root)

    update_threads_db(root / "state_5.sqlite", thread.thread_id, new_title)
    upsert_session_index(root / "session_index.jsonl", thread.thread_id, new_title, thread.updated_at_ms)
    update_session_jsonl(session_path, thread.thread_id, new_title)
    return backup_dir


def backup_file(path: Path, backup_dir: Path, root: Path) -> None:
    relative = path.relative_to(root)
    destination = backup_dir / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)


def prepare_mutation(root: Path) -> Path:
    full_backup_path = create_full_archive_backup(root)
    maybe_prompt_kill_vscode_server()
    return full_backup_path


def create_full_archive_backup(root: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = root.parent / f"{root.name}.bak.{timestamp}.tar.zst"

    print()
    print("Creating full backup archive before making changes:")
    print(f"  {backup_path}")

    try:
        subprocess.run(
            [
                "tar",
                "-C",
                str(root.parent),
                "--zstd",
                "-cf",
                str(backup_path),
                root.name,
            ],
            check=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("`tar` is not available; cannot create the required backup archive") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"backup archive creation failed with exit code {exc.returncode}") from exc

    print("Created full backup archive:")
    print(f"  {backup_path}")
    return backup_path


def maybe_prompt_kill_vscode_server() -> None:
    if not sys.stdin.isatty():
        print("Skipping vscode-server shutdown prompt because stdin is not interactive.")
        return

    user = os.environ.get("USER") or getpass.getuser()
    print()
    print("Safety step before touching Codex state:")
    print(f"  Optional command: pkill -u {user} -f vscode-server")
    print("  Waiting 10 seconds before asking, so this cannot be confirmed immediately", end="")
    for remaining in range(10, 0, -1):
        print(f".", end="", flush=True)
        time.sleep(1)
    print()

    if not prompt_yes_no(f"Run `pkill -u {user} -f vscode-server` now? [y/N]: "):
        #print("Continuing without killing vscode-server.")
        print("Must kill active vscode sessions to prevent live-lock!")
        sys.exit(1)

    try:
        completed = subprocess.run(
            ["pkill", "-u", user, "-f", "vscode-server"],
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("`pkill` is not available on PATH") from exc

    if completed.returncode == 0:
        print("Sent kill signal to matching vscode-server processes.")
    elif completed.returncode == 1:
        print("No matching vscode-server processes were found.")
    else:
        raise RuntimeError(f"`pkill` failed with exit code {completed.returncode}")


def sync_audits(
    root: Path, audits: list[AuditRecord], prune_foreign_events: bool
) -> tuple[Path, int]:
    backup_dir = root / ".chat_rename_backups" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_dir.mkdir(parents=True, exist_ok=False)

    backed_up: set[Path] = set()

    def ensure_backup(path: Path) -> None:
        if path in backed_up or not path.exists():
            return
        backup_file(path, backup_dir, root)
        backed_up.add(path)

    db_path = root / "state_5.sqlite"
    ensure_backup(db_path)
    for suffix in ("-wal", "-shm"):
        ensure_backup(root / f"state_5.sqlite{suffix}")
    index_path = root / "session_index.jsonl"
    ensure_backup(index_path)
    for audit in audits:
        ensure_backup(audit.session_path)

    changed = 0
    for audit in audits:
        apply_sync(root, audit, prune_foreign_events)
        changed += 1

    return backup_dir, changed


def apply_sync(root: Path, audit: AuditRecord, prune_foreign_events: bool) -> None:
    title = audit.canonical_title
    thread_id = audit.thread.thread_id
    update_threads_db(root / "state_5.sqlite", thread_id, title)
    upsert_session_index(root / "session_index.jsonl", thread_id, title, audit.thread.updated_at_ms)
    update_session_jsonl(
        audit.session_path,
        thread_id,
        title,
        prune_foreign_events=prune_foreign_events,
    )


def update_threads_db(db_path: Path, thread_id: str, new_title: str) -> None:
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.execute(
                "UPDATE threads SET title = ? WHERE id = ?",
                (new_title, thread_id),
            )
            if cur.rowcount != 1:
                raise RuntimeError(f"SQLite update touched {cur.rowcount} rows for {thread_id}")
            conn.commit()
    except sqlite3.OperationalError as exc:
        raise RuntimeError(
            "could not update state_5.sqlite; if this is your live ~/.codex folder, close VS Code/Codex first"
        ) from exc


def upsert_session_index(
    index_path: Path, thread_id: str, new_title: str, updated_at_ms: int
) -> None:
    rows: list[dict[str, Any]] = []
    found = False

    with index_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            if item.get("id") == thread_id:
                item["thread_name"] = new_title
                found = True
            rows.append(item)

    if not found:
        rows.append(
            {
                "id": thread_id,
                "thread_name": new_title,
                "updated_at": iso_from_ms(updated_at_ms),
            }
        )

    atomic_write_jsonl(index_path, rows)


def update_session_jsonl(
    session_path: Path,
    thread_id: str,
    new_title: str,
    prune_foreign_events: bool = False,
) -> None:
    rows: list[dict[str, Any]] = []
    found_index: int | None = None

    with session_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            item = json.loads(line)
            payload = item.get("payload", {})
            is_name_event = (
                item.get("type") == "event_msg"
                and payload.get("type") == "thread_name_updated"
            )
            if is_name_event and payload.get("thread_id") == thread_id:
                found_index = len(rows)
            elif is_name_event and prune_foreign_events:
                continue
            rows.append(item)

    if found_index is not None:
        rows[found_index]["payload"]["thread_name"] = new_title
    else:
        rows.append(
            {
                "timestamp": iso_now(),
                "type": "event_msg",
                "payload": {
                    "type": "thread_name_updated",
                    "thread_id": thread_id,
                    "thread_name": new_title,
                },
            }
        )

    atomic_write_jsonl(session_path, rows)


def atomic_write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as handle:
        tmp_path = Path(handle.name)
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True, separators=(",", ":")))
            handle.write("\n")
    tmp_path.replace(path)


def iso_from_ms(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms, tz=UTC).isoformat().replace("+00:00", "Z")


def iso_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
