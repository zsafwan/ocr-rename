from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_MAX_PAGES = 4
DEFAULT_CONCURRENCY = 5
DEFAULT_MAX_PDF_SIZE_MB = 30
FALLBACK_PAGES = [2, 1]
CONFIDENCE_THRESHOLD = 0.8


@dataclass
class Config:
    model: str = DEFAULT_MODEL
    max_pages: int = DEFAULT_MAX_PAGES
    concurrency: int = DEFAULT_CONCURRENCY
    max_pdf_size_mb: int = DEFAULT_MAX_PDF_SIZE_MB
    output_dir: Path = field(default_factory=lambda: Path("output"))
    batch_mode: bool = False
    resume: bool = False
    dry_run: bool = False

    def __post_init__(self):
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
