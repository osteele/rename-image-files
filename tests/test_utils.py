"""Tests for utility functions."""

from datetime import datetime
from pathlib import Path

import pytest

from rename_image_files.utils import (
    apply_case_style,
    get_filename_date,
    is_camera_filename,
    is_screenshot_filename,
    is_untitled_filename,
    needs_rename,
    read_exif_date,
    sanitize_filename,
)


def test_is_camera_filename() -> None:
    """Test camera filename detection."""
    # Test IMG prefixes
    assert is_camera_filename("IMG_1234.jpg")
    assert is_camera_filename("img_1234.jpg")
    assert is_camera_filename("IMG-1234.jpg")
    assert is_camera_filename("img-1234.jpg")

    # Test UUIDs
    assert is_camera_filename("63C0900B-4465-4CF9-A310-327C627DB9EA.jpg")
    assert is_camera_filename("63c0900b-4465-4cf9-a310-327c627db9ea.jpg")

    # Test non-camera filenames
    assert not is_camera_filename("photo.jpg")
    assert not is_camera_filename("vacation.jpg")
    assert not is_camera_filename("image_1234.jpg")


def test_is_screenshot_filename() -> None:
    """Test screenshot filename detection."""
    # Test various screenshot patterns
    assert is_screenshot_filename("Screenshot 2024-01-01.png")
    assert is_screenshot_filename("Screenshot 2024-01-01 at 10.30 AM.png")
    assert is_screenshot_filename("Screencap 2024-01-01.png")
    assert is_screenshot_filename("CleanShot 2024-01-01.png")
    assert is_screenshot_filename("ScreenFloat Shot.png")
    assert is_screenshot_filename("Pasted image 123.png")
    assert is_screenshot_filename("Picture 1.png")
    assert is_screenshot_filename("Picture 1 2.png")
    assert is_screenshot_filename("Skitch 2024-01-01.png")

    # Test non-screenshot filenames
    assert not is_screenshot_filename("photo.png")
    assert not is_screenshot_filename("vacation.png")
    assert not is_screenshot_filename("2024-01-01.png")


def test_is_untitled_filename() -> None:
    """Test untitled filename detection."""
    assert is_untitled_filename("untitled.jpg")
    assert is_untitled_filename("Untitled.jpg")
    assert is_untitled_filename("untitled 1.jpg")
    assert is_untitled_filename("Untitled 42.jpg")

    # Test non-untitled filenames
    assert not is_untitled_filename("photo.jpg")
    assert not is_untitled_filename("untitled-photo.jpg")
    assert not is_untitled_filename("my-untitled-work.jpg")


def test_needs_rename() -> None:
    """Test filename rename detection."""
    # Test camera filenames
    assert needs_rename("IMG_1234.jpg")
    assert needs_rename("63C0900B-4465-4CF9-A310-327C627DB9EA.jpg")

    # Test screenshot filenames
    assert needs_rename("Screenshot 2024-01-01.png")
    assert needs_rename("CleanShot 2024-01-01.png")

    # Test untitled filenames
    assert needs_rename("untitled.jpg")
    assert needs_rename("Untitled 1.jpg")

    # Test filenames that don't need renaming
    assert not needs_rename("vacation-photo.jpg")
    assert not needs_rename("golden-gate-bridge.png")
    assert not needs_rename("2024-01-01-party.jpg")


def test_sanitize_filename() -> None:
    """Test filename sanitization."""
    # Test basic sanitization with defaults (preserve case, punctuation, and spaces)
    assert sanitize_filename("Hello, World!") == "Hello, World!"
    assert sanitize_filename("Hello World") == "Hello World"
    assert sanitize_filename("Hello__World") == "Hello__World"

    # Test punctuation removal (keeps spaces and case)
    assert sanitize_filename("Hello, World!", allow_punctuation=False) == "Hello World"
    assert sanitize_filename("Hello—World", allow_punctuation=False) == "Hello-World"  # em dash
    assert sanitize_filename("Hello_World", allow_punctuation=False) == "Hello_World"  # underscore preserved

    # Test space replacement (keeps punctuation and case)
    assert sanitize_filename("Hello World", allow_spaces=False) == "Hello-World"
    assert sanitize_filename("Hello  World", allow_spaces=False) == "Hello-World"

    # Test case conversion
    assert sanitize_filename("Hello World", allow_uppercase=False) == "hello world"
    assert sanitize_filename("HELLO WORLD", allow_uppercase=False) == "hello world"

    # Test combinations
    assert sanitize_filename("Hello, World!", allow_spaces=False, allow_punctuation=False) == "Hello-World"
    assert (
        sanitize_filename("Hello, World!", allow_spaces=False, allow_punctuation=False, allow_uppercase=False)
        == "hello-world"
    )

    # Test with accents and non-ASCII
    assert sanitize_filename("Café.jpg") == "Café.jpg"
    assert sanitize_filename("Café.jpg", allow_accents=False) == "Cafe.jpg"
    assert sanitize_filename("Café.jpg", require_ascii=True) == "Cafe.jpg"

    # Test edge cases
    assert sanitize_filename("") == ""
    assert sanitize_filename("---test---", allow_punctuation=False) == "test"
    assert sanitize_filename("   spaces   ") == "spaces"  # leading/trailing spaces always removed


def test_apply_case_style() -> None:
    """Test case style application."""
    # Test different case styles
    assert apply_case_style("hello world", "lower") == "hello world"
    assert apply_case_style("hello world", "upper") == "HELLO WORLD"
    assert apply_case_style("hello world", "title") == "Hello World"
    assert apply_case_style("hello world", "sentence") == "Hello world"

    # Test with None case style
    assert apply_case_style("Hello World", None) == "Hello World"

    # Test with mixed case input
    assert apply_case_style("hElLo WoRlD", "lower") == "hello world"
    assert apply_case_style("hElLo WoRlD", "upper") == "HELLO WORLD"

    # Test with empty string
    assert apply_case_style("", "lower") == ""
    assert apply_case_style("", "upper") == ""


@pytest.fixture
def sample_image(tmp_path: Path) -> Path:
    """Create a sample test image."""
    image_path = tmp_path / "test.jpg"
    with open(image_path, "wb") as f:
        f.write(b"")  # Write empty file for testing
    return image_path


def test_get_filename_date() -> None:
    """Test date extraction from filenames."""
    # Test various date formats in filenames
    assert get_filename_date("2024-01-01-photo.jpg") == datetime(2024, 1, 1)
    assert get_filename_date("20240101_photo.jpg") == datetime(2024, 1, 1)
    assert get_filename_date("Screenshot 2024-01-01.png") == datetime(2024, 1, 1)
    assert get_filename_date("photo-2024-01-01-at-10-30.jpg") == datetime(2024, 1, 1)

    # Test filenames without dates
    assert get_filename_date("photo.jpg") is None
    assert get_filename_date("vacation.png") is None
    assert get_filename_date("IMG_1234.jpg") is None


def test_read_exif_date(sample_image: Path) -> None:
    """Test EXIF date extraction."""
    # Test with no EXIF data
    assert read_exif_date(str(sample_image)) is None

    # Note: Testing with actual EXIF data would require creating images with EXIF metadata,
    # which is beyond the scope of this basic test suite. Consider adding more comprehensive
    # tests with mock EXIF data or real sample images in the future.
