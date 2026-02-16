import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from .config import Config
from .api_client import (
    analyze_batch,
    analyze_realtime,
    get_batch_results,
    get_batch_status,
)
from .renamer import apply_undo, rename_files
from .review_file import read_csv, write_csv


def get_pdf_files(directory: Path) -> list[Path]:
    """Get all PDF files in a directory, sorted by name."""
    files = sorted(directory.glob("*.pdf"), key=lambda p: p.name)
    if not files:
        print(f"No PDF files found in {directory}")
        sys.exit(1)
    return files


def get_already_done(output_dir: Path) -> set[str]:
    """Scan existing review CSVs to find already-processed filenames."""
    done = set()
    for csv_path in output_dir.glob("review_*.csv"):
        try:
            entries = read_csv(csv_path)
            for e in entries:
                if e.suggested_title not in ("ERROR", "PARSE_ERROR"):
                    done.add(e.original_filename)
        except Exception:
            continue
    return done


def cmd_analyze(args):
    """Analyze PDFs and generate review CSV."""
    pdf_dir = Path(args.directory).resolve()
    if not pdf_dir.is_dir():
        print(f"Error: {pdf_dir} is not a directory")
        sys.exit(1)

    config = Config(
        model=args.model,
        max_pages=args.pages,
        concurrency=args.concurrency,
        output_dir=Path(args.output),
        batch_mode=args.batch,
        resume=args.resume,
    )

    pdf_files = get_pdf_files(pdf_dir)
    print(f"Found {len(pdf_files)} PDF files in {pdf_dir}")
    print(f"Model: {config.model}")

    already_done = get_already_done(config.output_dir) if config.resume else None

    if config.batch_mode:
        batch_id = analyze_batch(pdf_files, config, already_done)
        if batch_id:
            # Save batch ID for later retrieval
            batch_file = config.output_dir / "last_batch_id.txt"
            batch_file.write_text(batch_id)
    else:
        entries = analyze_realtime(pdf_files, config, already_done)
        if entries:
            csv_path = write_csv(entries, config.output_dir)
            print(f"\nReview CSV saved: {csv_path}")
            print(f"Open in Excel/Sheets, review the 'approve' column, then run:")
            print(f"  ocr-rename rename {csv_path} --dir {pdf_dir}")


def cmd_rename(args):
    """Rename files based on reviewed CSV."""
    csv_path = Path(args.csv_file).resolve()
    if not csv_path.exists():
        print(f"Error: {csv_path} not found")
        sys.exit(1)

    pdf_dir = Path(args.dir).resolve()
    if not pdf_dir.is_dir():
        print(f"Error: {pdf_dir} is not a directory")
        sys.exit(1)

    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    entries = read_csv(csv_path)
    approved = [e for e in entries if e.approve == "yes"]
    print(f"Found {len(entries)} entries, {len(approved)} approved for rename")

    if args.dry_run:
        print("\n--- DRY RUN (no files will be changed) ---\n")

    rename_files(pdf_dir, entries, dry_run=args.dry_run, output_dir=output_dir)


def cmd_undo(args):
    """Undo renames using a log file."""
    log_path = Path(args.log_file).resolve()
    if not log_path.exists():
        print(f"Error: {log_path} not found")
        sys.exit(1)

    pdf_dir = Path(args.dir).resolve()
    if not pdf_dir.is_dir():
        print(f"Error: {pdf_dir} is not a directory")
        sys.exit(1)

    apply_undo(log_path, pdf_dir)


def cmd_batch_status(args):
    """Check batch status."""
    get_batch_status(args.batch_id)


def cmd_batch_results(args):
    """Retrieve batch results and generate CSV."""
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    entries = get_batch_results(args.batch_id)
    if entries:
        csv_path = write_csv(entries, output_dir)
        print(f"\nReview CSV saved: {csv_path}")
        print(f"Open in Excel/Sheets, review the 'approve' column, then run:")
        print(f"  ocr-rename rename {csv_path} --dir <pdf_directory>")


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        prog="ocr-rename",
        description="Rename scanned PDF books using Claude Vision",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- analyze ---
    p_analyze = subparsers.add_parser(
        "analyze", help="Analyze PDFs and generate a review CSV")
    p_analyze.add_argument("directory", help="Directory containing PDF files")
    p_analyze.add_argument(
        "--model", default="claude-haiku-4-5-20251001",
        help="Claude model to use (default: claude-haiku-4-5-20251001)")
    p_analyze.add_argument(
        "--pages", type=int, default=4,
        help="Max pages to extract per PDF (default: 4)")
    p_analyze.add_argument(
        "--concurrency", type=int, default=5,
        help="Number of concurrent API requests (default: 5)")
    p_analyze.add_argument(
        "--output", default="output",
        help="Output directory for review CSV (default: output)")
    p_analyze.add_argument(
        "--batch", action="store_true",
        help="Use Batch API (50%% cost savings, slower)")
    p_analyze.add_argument(
        "--resume", action="store_true",
        help="Skip files already in existing review CSVs")

    # --- rename ---
    p_rename = subparsers.add_parser(
        "rename", help="Rename files based on reviewed CSV")
    p_rename.add_argument("csv_file", help="Path to reviewed CSV file")
    p_rename.add_argument(
        "--dir", required=True,
        help="Directory containing the PDF files to rename")
    p_rename.add_argument(
        "--dry-run", action="store_true",
        help="Preview renames without executing")
    p_rename.add_argument(
        "--output", default="output",
        help="Output directory for rename log (default: output)")

    # --- undo ---
    p_undo = subparsers.add_parser(
        "undo", help="Undo renames using a log file")
    p_undo.add_argument("log_file", help="Path to rename log JSON file")
    p_undo.add_argument(
        "--dir", required=True,
        help="Directory containing the renamed PDF files")

    # --- batch-status ---
    p_bstatus = subparsers.add_parser(
        "batch-status", help="Check batch processing status")
    p_bstatus.add_argument("batch_id", help="Batch ID to check")

    # --- batch-results ---
    p_bresults = subparsers.add_parser(
        "batch-results", help="Retrieve batch results and generate CSV")
    p_bresults.add_argument("batch_id", help="Batch ID to retrieve results for")
    p_bresults.add_argument(
        "--output", default="output",
        help="Output directory for review CSV (default: output)")

    args = parser.parse_args()

    commands = {
        "analyze": cmd_analyze,
        "rename": cmd_rename,
        "undo": cmd_undo,
        "batch-status": cmd_batch_status,
        "batch-results": cmd_batch_results,
    }
    commands[args.command](args)
