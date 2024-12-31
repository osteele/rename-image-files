from pathlib import Path
from unittest.mock import Mock, patch

import click
import pytest
from PIL import Image

# Mock llm module
mock_model = Mock()
mock_model.prompt.return_value = Mock(text=lambda: "test image description")
mock_get_model = Mock(return_value=mock_model)

with patch.dict(
    "sys.modules",
    {
        "llm": Mock(get_model=mock_get_model, Model=Mock),
    },
):
    from rename_image_files.cli import generate_filename
    from rename_image_files.utils import (
        get_exif_date,
        is_camera_filename,
        sanitize_filename,
    )


@pytest.fixture
def sample_image(tmp_path: Path) -> str:
    """Create a sample test image."""
    image_path = tmp_path / "test.jpg"
    # Create a 1x1 black image
    img = Image.new("RGB", (1, 1), color="black")
    img.save(image_path)
    return str(image_path)


def test_generate_filename(sample_image: str) -> None:
    """Test that generate_filename produces a valid filename."""
    mock_model.prompt.return_value = Mock(text=lambda: "Sunset over Golden Gate Bridge")
    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
        result = generate_filename(mock_model, sample_image)
        assert result == "sunset-over-golden-gate-bridge"


def test_generate_filename_special_chars(sample_image: str) -> None:
    """Test that generate_filename handles special characters."""
    mock_model.prompt.return_value = Mock(text=lambda: "Test! @#$% Image")
    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
        result = generate_filename(mock_model, sample_image)
        assert result == "test-image"
        assert all(c.isalnum() or c == "-" for c in result)


def test_generate_filename_no_api_key(sample_image: str) -> None:
    """Test that generate_filename raises an error when API key is not set."""
    with patch.dict("os.environ", clear=True):
        with pytest.raises(click.ClickException) as exc_info:
            generate_filename(mock_model, sample_image)
        assert "OPENAI_API_KEY environment variable not set" in str(exc_info.value)


def test_get_exif_date(tmp_path: Path) -> None:
    """Test that get_exif_date returns None for an image without EXIF data."""
    # Test with no date
    image_path = tmp_path / "test.jpg"
    img = Image.new("RGB", (1, 1), color="black")
    img.save(image_path)
    result = get_exif_date(str(image_path))
    assert result is None

    # Test with date in filename
    image_path = tmp_path / "2024-12-31 IMG_1721.jpg"
    img.save(image_path)
    result = get_exif_date(str(image_path))
    assert result is not None
    assert result.year == 2024
    assert result.month == 12
    assert result.day == 31

    # Test with compact date in filename
    image_path = tmp_path / "20241231_photo.jpg"
    img.save(image_path)
    result = get_exif_date(str(image_path))
    assert result is not None
    assert result.year == 2024
    assert result.month == 12
    assert result.day == 31


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

    # Test non-matching names
    assert not is_camera_filename("photo.jpg")
    assert not is_camera_filename("image_1234.jpg")
    assert not is_camera_filename("picture.jpg")
    assert not is_camera_filename(
        "63C0900B4465-4CF9-A310-327C627DB9EA.jpg"
    )  # Invalid UUID


def test_sanitize_filename() -> None:
    """Test filename sanitization."""
    test_cases = [
        # Basic conversion
        ("Hello World", "hello-world"),
        # Special characters
        ("Hello! @#$% World", "hello-world"),
        # Multiple spaces and punctuation
        ("Hello,  World!!!", "hello-world"),
        # Unicode characters
        ("Café & Résumé", "cafe-resume"),
        # Leading/trailing spaces and hyphens
        (" -Hello World- ", "hello-world"),
        # Numbers
        ("Photo 123", "photo-123"),
        # Multiple hyphens
        ("Hello - - World", "hello-world"),
        # Mixed case
        ("HeLLo WoRLD", "hello-world"),
        # Underscores
        ("hello_world", "hello-world"),
    ]

    for input_text, expected in test_cases:
        result = sanitize_filename(input_text)
        assert result == expected
        # Verify the result is filename-safe
        assert all(c.isalnum() or c == "-" for c in result)
        assert not result.startswith("-")
        assert not result.endswith("-")
