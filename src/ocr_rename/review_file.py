import csv
import io
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import CONFIDENCE_THRESHOLD


@dataclass
class ReviewEntry:
    original_filename: str
    suggested_title: str
    suggested_author: str
    new_filename: str
    confidence: float
    approve: str
    language: str = ""
    edition: str = ""
    notes: str = ""


def sanitize_filename(name: str) -> str:
    """Remove or replace characters that are invalid in filenames."""
    invalid = '<>:"/\\|?*'
    for ch in invalid:
        name = name.replace(ch, "")
    # Collapse multiple spaces and strip
    name = " ".join(name.split())
    # Truncate to reasonable length (255 chars minus .pdf)
    if len(name) > 240:
        name = name[:240]
    return name


def build_new_filename(title: str, author: str) -> str:
    """Build 'Title - Author.pdf' filename."""
    if author and author != "Unknown":
        name = f"{title} - {author}"
    else:
        name = title
    return sanitize_filename(name) + ".pdf"


def make_entry(original_filename: str, result: dict) -> ReviewEntry:
    """Create a ReviewEntry from API result."""
    title = result.get("title", "Unknown")
    author = result.get("author", "Unknown")
    confidence = float(result.get("confidence", 0))
    new_filename = build_new_filename(title, author)
    approve = "yes" if confidence >= CONFIDENCE_THRESHOLD else "review"

    return ReviewEntry(
        original_filename=original_filename,
        suggested_title=title,
        suggested_author=author,
        new_filename=new_filename,
        confidence=confidence,
        approve=approve,
        language=result.get("language", ""),
        edition=result.get("edition") or "",
        notes=result.get("notes") or "",
    )


FIELDNAMES = [
    "original_filename", "suggested_title", "suggested_author",
    "new_filename", "confidence", "approve", "language", "edition", "notes",
]


def write_csv(entries: list[ReviewEntry], output_dir: Path) -> Path:
    """Write review entries to a UTF-8 BOM CSV file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"review_{timestamp}.csv"

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for entry in entries:
            writer.writerow({
                "original_filename": entry.original_filename,
                "suggested_title": entry.suggested_title,
                "suggested_author": entry.suggested_author,
                "new_filename": entry.new_filename,
                "confidence": entry.confidence,
                "approve": entry.approve,
                "language": entry.language,
                "edition": entry.edition,
                "notes": entry.notes,
            })

    return csv_path


def read_csv(csv_path: Path) -> list[ReviewEntry]:
    """Read review entries from a CSV file."""
    entries = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entries.append(ReviewEntry(
                original_filename=row["original_filename"],
                suggested_title=row["suggested_title"],
                suggested_author=row["suggested_author"],
                new_filename=row["new_filename"],
                confidence=float(row["confidence"]),
                approve=row["approve"].strip().lower(),
                language=row.get("language", ""),
                edition=row.get("edition", ""),
                notes=row.get("notes", ""),
            ))
    return entries
