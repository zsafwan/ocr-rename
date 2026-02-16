# PDF Book Renamer

Rename scanned PDF books using Claude Vision. Extracts book title and author from cover/title pages (works with Arabic calligraphy, English, Persian, etc.) and renames files to `Title - Author.pdf`.

## Requirements

- Python 3.10+
- An Anthropic API key ([get one here](https://console.anthropic.com))

## Setup

```bash
# Clone the repo
git clone https://github.com/zsafwan/ocr-rename.git
cd ocr-rename

# Create a virtual environment
python -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate

# Install
pip install -e .
```

Create a `.env` file in the project root with your API key:

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

### Step 1: Analyze PDFs

```bash
ocr-rename analyze "C:\path\to\your\pdfs"
```

This sends the first few pages of each PDF to Claude, extracts title/author, and generates a review CSV in `output/`.

### Step 2: Review the CSV

Open `output/review_TIMESTAMP.csv` in Excel. Arabic text displays correctly. Check the `approve` column — high-confidence results are auto-set to `yes`, lower ones to `review`. Edit as needed.

### Step 3: Rename

```bash
# Preview first (no files changed)
ocr-rename rename output/review_TIMESTAMP.csv --dir "C:\path\to\your\pdfs" --dry-run

# Apply renames
ocr-rename rename output/review_TIMESTAMP.csv --dir "C:\path\to\your\pdfs"
```

### Undo

Every rename generates a log file. To reverse:

```bash
ocr-rename undo output/rename_log_TIMESTAMP.json --dir "C:\path\to\your\pdfs"
```

## Options

```bash
# Use a different model (default: Haiku — cheapest)
ocr-rename analyze /path/to/pdfs --model claude-sonnet-4-5-20250929

# Use Batch API for large runs (50% cheaper, takes a few hours)
ocr-rename analyze /path/to/pdfs --batch

# Resume after interruption (skips already-processed files)
ocr-rename analyze /path/to/pdfs --resume

# Check batch status / get results
ocr-rename batch-status <batch_id>
ocr-rename batch-results <batch_id>
```

## Cost Estimates

| Files | Model | Mode | Est. Cost |
|-------|-------|------|-----------|
| 45 | Haiku 4.5 | Real-time | ~$0.35 |
| 45 | Sonnet 4.5 | Real-time | ~$2-3 |
| 3,000 | Haiku 4.5 | Batch | ~$22-30 |
| 3,000 | Sonnet 4.5 | Batch | ~$65-80 |
