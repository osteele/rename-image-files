"""Utility functions for rename-image-files."""

import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Final

import exifread

# UUID pattern matches strings that look like UUIDs
UUID_PATTERN: Final = re.compile(
    r"^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$",
    re.IGNORECASE,
)


def is_camera_filename(filename: str) -> bool:
    """Check if a filename matches camera filename patterns.

    Matches:
    - Names starting with 'IMG-' or 'IMG_' (case insensitive)
    - Names that look like UUIDs (e.g. 63C0900B-4465-4CF9-A310-327C627DB9EA)
    """
    stem = Path(filename).stem
    return stem.upper().startswith(("IMG-", "IMG_")) or bool(UUID_PATTERN.match(stem))


def sanitize_filename(text: str) -> str:
    """Convert text into a safe filename.

    - Converts to lowercase
    - Replaces spaces and punctuation with hyphens
    - Removes non-ASCII characters
    - Collapses multiple hyphens
    - Trims hyphens from ends
    """
    # Normalize unicode characters
    text = unicodedata.normalize("NFKD", text)
    # Remove accents
    text = "".join(c for c in text if not unicodedata.combining(c))
    # Convert to ASCII, lowercase
    text = text.encode("ascii", "ignore").decode().lower()
    # Replace underscores with hyphens first
    text = text.replace("_", "-")
    # Replace spaces and punctuation with hyphens
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    # Remove leading/trailing hyphens
    return text.strip("-")


def get_exif_date(image_path: str) -> datetime | None:
    """Extract the date from image EXIF data or filename.

    Tries to get the date from:
    1. EXIF DateTimeOriginal
    2. Filename patterns like YYYY-MM-DD
    """
    # Try EXIF data first
    with open(image_path, "rb") as f:
        tags = exifread.process_file(f, details=False)
        date_taken = tags.get("EXIF DateTimeOriginal")
        if date_taken:
            return datetime.strptime(str(date_taken), "%Y:%m:%d %H:%M:%S")

    # Try filename patterns
    filename = Path(image_path).stem
    date_patterns = [
        # YYYY-MM-DD
        r"(?P<year>20\d{2})-(?P<month>\d{2})-(?P<day>\d{2})",
        # YYYYMMDD
        r"(?P<year>20\d{2})(?P<month>\d{2})(?P<day>\d{2})",
    ]

    for pattern in date_patterns:
        match = re.search(pattern, filename)
        if match:
            groups = match.groupdict()
            try:
                return datetime(
                    year=int(groups["year"]),
                    month=int(groups["month"]),
                    day=int(groups["day"]),
                )
            except ValueError:
                continue

    return None
