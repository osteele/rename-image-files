"""Utility functions for rename-image-files."""

import logging
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


def is_screenshot_filename(filename: str) -> bool:
    """Check if a filename matches screenshot or screen capture patterns.

    Matches:
    - Pasted image with numbers
    - Untitled with optional numbers
    - CleanShot with date
    - ScreenFloat Shot
    - Various screenshot/screencap patterns with dates and timestamps
    - Picture with numbers
    - Skitch with date
    """
    patterns = [
        r"^CleanShot \d{4}-\d{2}-\d{2}",
        r"^ScreenFloat Shot",
        r"^Screen(shot|cap)(\s\d+)?\s?\d{4}-\d{2}-\d{2}(?:\s\w+\s\d{1,2}\.\d{1,2}\s?\w+)?$",
        r"^Pasted image \d+",
        r"^Picture \d+(?:\s\d+)?$",
        r"^Skitch \d{4}-\d{2}-\d{2}$",
    ]
    stem = Path(filename).stem
    return any(re.match(p, stem, re.IGNORECASE) for p in patterns)


def is_untitled_filename(filename: str) -> bool:
    """Check if a filename matches untitled patterns."""
    stem = Path(filename).stem
    return bool(re.match(r"^untitled(\s\d+)?$", stem, re.IGNORECASE))


def needs_rename(filename: str) -> bool:
    """Check if a filename needs to be renamed.

    Returns True if the filename matches camera or screenshot patterns."""
    return is_camera_filename(filename) or is_screenshot_filename(filename) or is_untitled_filename(filename)


def sanitize_filename(
    text: str,
    *,
    allow_accents: bool = True,
    allow_punctuation: bool = True,
    allow_spaces: bool = True,
    allow_uppercase: bool = True,
    require_ascii: bool = False,
) -> str:
    """Convert text into a safe filename.

    Args:
        text: The text to convert
        allow_accents: Whether to allow accented characters
        allow_punctuation: Whether to allow punctuation. When False, punctuation is removed except
            for hyphens and underscores which are always preserved
        allow_spaces: Whether to allow spaces. When False, spaces are converted to hyphens.
            Leading and trailing spaces are always removed
        allow_uppercase: Whether to allow uppercase characters
        require_ascii: Whether to require ASCII characters only

    Returns:
        A safe filename
    """
    # Strip leading/trailing whitespace
    text = text.strip()

    # lowercase if needed (do this before accent removal)
    if not allow_uppercase:
        text = text.lower()

    if allow_accents and not require_ascii:
        # Use NFC for composed form (é instead of e + ́)
        text = unicodedata.normalize("NFC", text)
    else:
        # Use NFKD for decomposed form to remove accents
        text = unicodedata.normalize("NFKD", text)
        text = "".join(c for c in text if not unicodedata.combining(c))

    # Convert to ASCII if required
    if require_ascii:
        text = text.encode("ascii", "ignore").decode()

    # Handle punctuation
    if not allow_punctuation:
        # First normalize all dash-like characters to hyphens
        text = re.sub(r"[\u2010-\u2015]", "-", text)  # various dash characters
        # Remove all punctuation except hyphens and underscores
        text = re.sub(r"[^\w\s-]", "", text)
        # Normalize spaces
        text = re.sub(r"\s+", " ", text)

    # Handle spaces
    if not allow_spaces:
        text = re.sub(r"\s+", "-", text)

    # Collapse multiple hyphens (if any were created)
    text = re.sub(r"-+", "-", text)
    # Strip hyphens from ends
    text = text.strip("-")

    return text


def read_exif_date(image_path: str) -> datetime | None:
    """Read the date from image EXIF metadata.

    This function only reads dates from EXIF metadata. It does not look at filenames
    or other sources. For dates in filenames, use get_filename_date instead.

    Args:
        image_path: Path to the image file

    Returns:
        The date from EXIF metadata, or None if no EXIF date was found
    """
    if image_path.lower() not in (".jpg", ".jpeg"):
        return None

    try:
        with open(image_path, "rb") as f:
            logging.debug(f"Reading EXIF from {image_path}")
            tags = exifread.process_file(f)
            logging.debug(f"Found EXIF tags: {list(tags.keys())}")
            if "EXIF DateTimeOriginal" in tags:
                date_str = str(tags["EXIF DateTimeOriginal"])
                return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
            elif "Image DateTime" in tags:
                date_str = str(tags["Image DateTime"])
                return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
    except OSError as e:
        logging.error(f"OSError reading EXIF: {e}")
    except KeyError as e:
        logging.error(f"KeyError reading EXIF: {e}")
    except ValueError as e:
        logging.error(f"ValueError reading EXIF: {e}")
    except Exception as e:
        logging.error(f"Unexpected error reading EXIF: {e}")
        logging.exception('Exception occurred while processing EXIF date')
    return None


def get_filename_date(image_path: str) -> datetime | None:
    """Extract the date from the filename."""
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


def apply_case_style(text: str, case_style: str | None) -> str:
    """Apply the specified case style to text.

    Args:
        text: The text to apply case style to
        case_style: The case style to apply. One of 'lower', 'upper', 'title', 'sentence', or None

    Returns:
        The text with the specified case style applied
    """
    if not text or case_style is None:
        return text

    match case_style:
        case "lower":
            return text.lower()
        case "upper":
            return text.upper()
        case "title":
            return text.title()
        case "sentence":
            return text.capitalize()
        case _:
            return text
