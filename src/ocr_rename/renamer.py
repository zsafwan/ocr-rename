import json
from datetime import datetime
from pathlib import Path

from .review_file import ReviewEntry


def resolve_conflicts(pdf_dir: Path, entries: list[ReviewEntry]) -> list[ReviewEntry]:
    """Append (2), (3), etc. to filenames that would collide."""
    seen: dict[str, int] = {}
    # Include existing files in the directory
    for f in pdf_dir.iterdir():
        if f.suffix.lower() == ".pdf":
            seen[f.name.lower()] = 1

    resolved = []
    for entry in entries:
        name = entry.new_filename
        key = name.lower()
        # Don't conflict with original if it's the same file
        if key == entry.original_filename.lower():
            resolved.append(entry)
            if key not in seen:
                seen[key] = 1
            continue

        if key in seen:
            stem = name[:-4]  # remove .pdf
            counter = seen[key] + 1
            while True:
                candidate = f"{stem} ({counter}).pdf"
                if candidate.lower() not in seen:
                    name = candidate
                    break
                counter += 1
            seen[name.lower()] = 1
        else:
            seen[key] = 1

        entry.new_filename = name
        resolved.append(entry)

    return resolved


def rename_files(pdf_dir: Path, entries: list[ReviewEntry],
                 dry_run: bool = False, output_dir: Path | None = None) -> list[dict]:
    """Rename files according to approved entries. Returns rename log."""
    approved = [e for e in entries if e.approve == "yes"]
    approved = resolve_conflicts(pdf_dir, approved)

    log_entries = []
    skipped = 0
    renamed = 0
    errors = 0

    for entry in approved:
        src = pdf_dir / entry.original_filename
        dst = pdf_dir / entry.new_filename

        if not src.exists():
            print(f"  SKIP (not found): {entry.original_filename}")
            skipped += 1
            continue

        if src.name == entry.new_filename:
            print(f"  SKIP (same name): {entry.original_filename}")
            skipped += 1
            continue

        log_entry = {
            "original": entry.original_filename,
            "new": entry.new_filename,
            "status": "pending",
        }

        if dry_run:
            print(f"  WOULD RENAME: {entry.original_filename}")
            print(f"            ->  {entry.new_filename}")
            log_entry["status"] = "dry_run"
        else:
            try:
                src.rename(dst)
                print(f"  RENAMED: {entry.original_filename}")
                print(f"       ->  {entry.new_filename}")
                log_entry["status"] = "renamed"
                renamed += 1
            except OSError as e:
                print(f"  ERROR: {entry.original_filename} -> {e}")
                log_entry["status"] = f"error: {e}"
                errors += 1

        log_entries.append(log_entry)

    print(f"\nSummary: {renamed} renamed, {skipped} skipped, {errors} errors")

    # Save rename log for undo
    if log_entries and not dry_run and output_dir:
        log_path = _save_log(log_entries, output_dir)
        print(f"Rename log saved: {log_path}")

    return log_entries


def _save_log(log_entries: list[dict], output_dir: Path) -> Path:
    """Save rename log to JSON file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = output_dir / f"rename_log_{timestamp}.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_entries, f, ensure_ascii=False, indent=2)
    return log_path


def undo_renames(log_path: Path) -> None:
    """Reverse renames using a rename log file."""
    with open(log_path, "r", encoding="utf-8") as f:
        log_entries = json.load(f)

    # Determine the directory from the first entry
    # The log doesn't store the directory, so we need it passed or inferred
    # We'll look for the renamed files in the same directory as the log
    # Actually, we need the user to specify the directory, or we store it in the log
    # For now, let's ask for it in CLI

    reversed_count = 0
    errors = 0

    for entry in reversed(log_entries):
        if entry["status"] != "renamed":
            continue

        # These paths are relative filenames; we need the directory
        # This will be handled by the CLI passing pdf_dir
        print(f"  Log entry: {entry['new']} -> {entry['original']}")

    print(f"\nFound {sum(1 for e in log_entries if e['status'] == 'renamed')} "
          f"renames to reverse.")
    print("Use 'ocr-rename undo <log_file> --dir <pdf_directory>' to apply.")


def apply_undo(log_path: Path, pdf_dir: Path) -> None:
    """Actually reverse the renames."""
    with open(log_path, "r", encoding="utf-8") as f:
        log_entries = json.load(f)

    reversed_count = 0
    errors = 0

    for entry in reversed(log_entries):
        if entry["status"] != "renamed":
            continue

        src = pdf_dir / entry["new"]
        dst = pdf_dir / entry["original"]

        if not src.exists():
            print(f"  SKIP (not found): {entry['new']}")
            continue

        try:
            src.rename(dst)
            print(f"  UNDONE: {entry['new']} -> {entry['original']}")
            reversed_count += 1
        except OSError as e:
            print(f"  ERROR: {entry['new']} -> {e}")
            errors += 1

    print(f"\nUndo summary: {reversed_count} reversed, {errors} errors")
