import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import anthropic
from tqdm import tqdm

from .config import Config
from .pdf_utils import extract_first_pages, pdf_to_base64
from .prompt import SYSTEM_PROMPT, USER_PROMPT
from .review_file import ReviewEntry, make_entry


class RateLimiter:
    """Simple token-bucket rate limiter for API requests."""

    def __init__(self, max_per_minute: int = 50):
        self.max_per_minute = max_per_minute
        self.interval = 60.0 / max_per_minute
        self.lock = threading.Lock()
        self.last_request = 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_request
            if elapsed < self.interval:
                time.sleep(self.interval - elapsed)
            self.last_request = time.monotonic()


def _parse_response(text: str) -> dict:
    """Parse JSON from Claude's response, handling markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        # Remove markdown code fences
        lines = text.split("\n")
        # Remove first line (```json or ```) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    return json.loads(text)


def analyze_single(client: anthropic.Anthropic, pdf_path: Path,
                   config: Config) -> ReviewEntry | None:
    """Analyze a single PDF and return a ReviewEntry."""
    try:
        pdf_bytes = extract_first_pages(pdf_path, config.max_pages, config.max_pdf_size_mb)
        b64_data = pdf_to_base64(pdf_bytes)

        response = client.messages.create(
            model=config.model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": b64_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": USER_PROMPT,
                    },
                ],
            }],
        )

        result = _parse_response(response.content[0].text)
        entry = make_entry(pdf_path.name, result)

        usage = response.usage
        return entry, usage.input_tokens, usage.output_tokens

    except json.JSONDecodeError as e:
        print(f"\n  WARNING: Failed to parse response for {pdf_path.name}: {e}")
        entry = make_entry(pdf_path.name, {
            "title": "PARSE_ERROR",
            "author": "Unknown",
            "confidence": 0,
            "notes": f"Response parse error: {e}",
        })
        return entry, 0, 0
    except Exception as e:
        print(f"\n  ERROR processing {pdf_path.name}: {e}")
        entry = make_entry(pdf_path.name, {
            "title": "ERROR",
            "author": "Unknown",
            "confidence": 0,
            "notes": str(e),
        })
        return entry, 0, 0


def analyze_realtime(pdf_files: list[Path], config: Config,
                     already_done: set[str] | None = None) -> list[ReviewEntry]:
    """Analyze PDFs using real-time API with concurrent workers."""
    client = anthropic.Anthropic()
    rate_limiter = RateLimiter(max_per_minute=50)

    files_to_process = pdf_files
    if already_done:
        files_to_process = [f for f in pdf_files if f.name not in already_done]
        if len(files_to_process) < len(pdf_files):
            print(f"Resuming: skipping {len(pdf_files) - len(files_to_process)} "
                  f"already-processed files")

    entries: list[ReviewEntry] = []
    total_input_tokens = 0
    total_output_tokens = 0

    def process_one(pdf_path: Path):
        rate_limiter.wait()
        return analyze_single(client, pdf_path, config)

    with ThreadPoolExecutor(max_workers=config.concurrency) as executor:
        futures = {executor.submit(process_one, f): f for f in files_to_process}

        with tqdm(total=len(files_to_process), desc="Analyzing PDFs",
                  unit="file") as pbar:
            for future in as_completed(futures):
                result = future.result()
                if result:
                    entry, in_tok, out_tok = result
                    entries.append(entry)
                    total_input_tokens += in_tok
                    total_output_tokens += out_tok
                pbar.update(1)

    print(f"\nTokens used: {total_input_tokens:,} input, "
          f"{total_output_tokens:,} output")
    _print_cost_estimate(total_input_tokens, total_output_tokens, config.model)

    return entries


def _print_cost_estimate(input_tokens: int, output_tokens: int, model: str):
    """Print estimated cost based on model pricing."""
    # Approximate pricing per million tokens
    pricing = {
        "claude-haiku-4-5-20251001": (1.00, 5.00),
        "claude-sonnet-4-5-20250929": (3.00, 15.00),
    }
    if model in pricing:
        in_price, out_price = pricing[model]
        cost = (input_tokens / 1_000_000 * in_price +
                output_tokens / 1_000_000 * out_price)
        print(f"Estimated cost: ${cost:.4f}")


def analyze_batch(pdf_files: list[Path], config: Config,
                  already_done: set[str] | None = None) -> str:
    """Submit PDFs to the Batch API. Returns batch ID for later retrieval."""
    client = anthropic.Anthropic()

    files_to_process = pdf_files
    if already_done:
        files_to_process = [f for f in pdf_files if f.name not in already_done]

    print(f"Preparing {len(files_to_process)} files for batch submission...")

    requests = []
    for pdf_path in tqdm(files_to_process, desc="Preparing PDFs", unit="file"):
        try:
            pdf_bytes = extract_first_pages(pdf_path, config.max_pages,
                                            config.max_pdf_size_mb)
            b64_data = pdf_to_base64(pdf_bytes)

            requests.append({
                "custom_id": pdf_path.name,
                "params": {
                    "model": config.model,
                    "max_tokens": 1024,
                    "system": SYSTEM_PROMPT,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": b64_data,
                                },
                            },
                            {
                                "type": "text",
                                "text": USER_PROMPT,
                            },
                        ],
                    }],
                },
            })
        except Exception as e:
            print(f"  ERROR preparing {pdf_path.name}: {e}")

    if not requests:
        print("No files to process.")
        return ""

    print(f"Submitting batch of {len(requests)} requests...")
    batch = client.messages.batches.create(requests=requests)
    print(f"Batch submitted! ID: {batch.id}")
    print(f"Status: {batch.processing_status}")
    print(f"\nTo check status:  ocr-rename batch-status {batch.id}")
    print(f"To get results:   ocr-rename batch-results {batch.id} <pdf_dir>")
    return batch.id


def get_batch_status(batch_id: str) -> None:
    """Check the status of a batch."""
    client = anthropic.Anthropic()
    batch = client.messages.batches.retrieve(batch_id)
    print(f"Batch ID: {batch.id}")
    print(f"Status: {batch.processing_status}")
    counts = batch.request_counts
    print(f"Requests: {counts.succeeded} succeeded, {counts.errored} errored, "
          f"{counts.processing} processing")


def get_batch_results(batch_id: str) -> list[ReviewEntry]:
    """Retrieve results from a completed batch."""
    client = anthropic.Anthropic()

    batch = client.messages.batches.retrieve(batch_id)
    if batch.processing_status != "ended":
        print(f"Batch not done yet. Status: {batch.processing_status}")
        return []

    entries = []
    result_stream = client.messages.batches.results(batch_id)
    for entry in result_stream:
        filename = entry.custom_id
        if entry.result.type == "succeeded":
            try:
                result = _parse_response(entry.result.message.content[0].text)
                entries.append(make_entry(filename, result))
            except (json.JSONDecodeError, IndexError) as e:
                entries.append(make_entry(filename, {
                    "title": "PARSE_ERROR",
                    "author": "Unknown",
                    "confidence": 0,
                    "notes": f"Parse error: {e}",
                }))
        else:
            entries.append(make_entry(filename, {
                "title": "API_ERROR",
                "author": "Unknown",
                "confidence": 0,
                "notes": f"Batch error: {entry.result.type}",
            }))

    return entries
