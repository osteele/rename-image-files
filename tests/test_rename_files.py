from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

import click
import pytest
from PIL import Image

from rename_image_files.generators import get_model

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
    from rename_image_files.generators import generate_filename
    from rename_image_files.utils import is_camera_filename, read_exif_date, sanitize_filename


@pytest.fixture
def sample_image() -> bytes:
    """Create a sample test image."""
    # Create a 1x1 black image
    img = Image.new("RGB", (1, 1), color="black")
    with BytesIO() as bio:
        img.save(bio, format="JPEG")
        return bio.getvalue()


@pytest.mark.skip(reason="todo: move this to a higher-level function")
def test_generate_filename(sample_image: bytes) -> None:
    """Test that generate_filename produces a valid filename."""
    mock_model.prompt.return_value = Mock(text=lambda: "Sunset over Golden Gate Bridge")
    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
        result = generate_filename(mock_model, sample_image)
        assert result == "sunset-over-golden-gate-bridge"


@pytest.mark.skip(reason="wip")
def test_generate_filename_special_chars(sample_image: bytes) -> None:
    """Test that generate_filename handles special characters."""
    mock_model.prompt.return_value = Mock(text=lambda: "Test! @#$% Image")
    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
        result = generate_filename(mock_model, sample_image)
        assert result == "test-image"
        assert all(c.isalnum() or c == "-" for c in result)


def test_generate_filename_no_api_key(sample_image: bytes) -> None:
    """Test that generate_filename raises an error when API key is not set."""
    with patch.dict("os.environ", clear=True):
        with pytest.raises(click.ClickException) as exc_info:
            _ = get_model("o1-mini")
        assert "OPENAI_API_KEY environment variable not set" in str(exc_info.value)


def test_read_exif_date(tmp_path: Path) -> None:
    """Test that read_exif_date returns None for an image without EXIF data."""
    # Test with no date
    image_path = tmp_path / "test.jpg"
    img = Image.new("RGB", (1, 1), color="black")
    img.save(image_path)
    result = read_exif_date(str(image_path))
    assert result is None

    # Test with date in filename
    image_path = tmp_path / "2024-12-31 IMG_1721.jpg"
    img.save(image_path)
    result = read_exif_date(str(image_path))
    assert result is None

    # Test with compact date in filename
    image_path = tmp_path / "20241231_photo.jpg"
    img.save(image_path)
    result = read_exif_date(str(image_path))
    assert result is None


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
    assert not is_camera_filename("63C0900B4465-4CF9-A310-327C627DB9EA.jpg")  # Invalid UUID


def test_sanitize_filename() -> None:
    """Test filename sanitization."""
    test_cases = [
        # Basic conversion with all sanitization options
        ("Hello World", "hello-world", {"allow_spaces": False, "allow_uppercase": False}),
        # Special characters
        (
            "Hello! @#$% World",
            "hello-world",
            {"allow_punctuation": False, "allow_uppercase": False, "allow_spaces": False},
        ),
        # Multiple spaces and punctuation
        (
            "Hello,  World!!!",
            "hello-world",
            {"allow_punctuation": False, "allow_uppercase": False, "allow_spaces": False},
        ),
        # Unicode characters
        (
            "Café & Résumé",
            "cafe-resume",
            {"allow_accents": False, "allow_punctuation": False, "allow_spaces": False, "allow_uppercase": False},
        ),
        # Leading/trailing spaces and hyphens
        (
            " -Hello World- ",
            "hello-world",
            {"allow_punctuation": False, "allow_uppercase": False, "allow_spaces": False},
        ),
        # Numbers
        ("Photo 123", "photo-123", {"allow_spaces": False, "allow_uppercase": False}),
        # Multiple hyphens (collapsed to single hyphen)
        (
            "Hello - - World",
            "hello-world",
            {"allow_punctuation": False, "allow_uppercase": False, "allow_spaces": False},
        ),
        # Mixed case
        ("HeLLo WoRLD", "hello-world", {"allow_spaces": False, "allow_uppercase": False}),
        # Underscores (preserved)
        ("hello_world", "hello_world", {"allow_punctuation": False}),
    ]

    for input_text, expected, options in test_cases:
        result = sanitize_filename(input_text, **options)
        assert result == expected, f"Failed for input: {input_text}"
