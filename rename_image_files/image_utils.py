import io
import logging
import platform
import subprocess
from pathlib import Path

from PIL import Image

try:
    import pillow_heif

    HAVE_PILLOW_HEIF = True
except ImportError:
    HAVE_PILLOW_HEIF = False


def convert_heic_to_jpeg(image_path: Path) -> bytes:
    """Convert HEIC to JPEG using pillow-heif or sips (macOS built-in)."""
    logging.debug(f"Starting HEIC conversion for {image_path}")
    # Try pillow-heif first if available
    if HAVE_PILLOW_HEIF:
        logging.debug("Attempting conversion with pillow-heif")
        try:
            heif_file = pillow_heif.read_heif(str(image_path))
            logging.debug("Successfully read HEIC file with pillow-heif")
            if heif_file.data is None:
                raise ValueError("No data in HEIC file")
            image = Image.frombytes(
                heif_file.mode,
                heif_file.size,
                heif_file.data,
                "raw",
                heif_file.mode,
                heif_file.stride,
            )
            logging.debug("Successfully created PIL Image from HEIC data")
            # Convert to RGB if needed
            if image.mode != "RGB":
                logging.debug(f"Converting from {image.mode} to RGB")
                image = image.convert("RGB")
            # Save to bytes
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format="JPEG")
            logging.debug("Successfully converted to JPEG")
            return img_byte_arr.getvalue()
        except Exception as e:
            logging.debug(f"pillow-heif conversion failed: {str(e)}")
            if platform.system() != "Darwin":
                raise RuntimeError(
                    f"Failed to convert HEIC using pillow-heif: {str(e)}. "
                    "Install ImageMagick for HEIC support on non-macOS platforms."
                )
            logging.debug("Falling back to sips")
            # On macOS, fall back to sips

    # Fall back to sips on macOS
    if platform.system() != "Darwin":
        raise RuntimeError(
            "HEIC conversion failed and sips is only available on macOS. "
            "Install ImageMagick for HEIC support on other platforms."
        )

    logging.debug("Attempting conversion with sips")
    # Create a temporary file for the JPEG
    temp_jpeg = image_path.with_suffix(".jpg.temp")
    try:
        # First, verify the HEIC file using sips
        logging.debug("Verifying HEIC file with sips")
        verify_result = subprocess.run(
            ["sips", "-g", "format", str(image_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if verify_result.returncode != 0:
            logging.debug(f"sips verification failed: {verify_result.stderr}")
            raise RuntimeError(f"Invalid or corrupted HEIC file: {image_path}\n" f"sips output: {verify_result.stderr}")

        logging.debug("Converting HEIC to JPEG with sips")
        # Convert HEIC to JPEG using sips
        convert_result = subprocess.run(
            ["sips", "-s", "format", "jpeg", str(image_path), "--out", str(temp_jpeg)],
            check=False,
            capture_output=True,
            text=True,
        )
        if convert_result.returncode != 0:
            logging.debug(f"sips conversion failed: {convert_result.stderr}")
            raise RuntimeError(
                f"Failed to convert HEIC to JPEG: {convert_result.stderr}\n"
                "This might be due to a corrupted HEIC file or an unsupported format."
            )

        logging.debug("Reading converted JPEG file")
        # Read the JPEG data
        with open(temp_jpeg, "rb") as f:
            return f.read()
    except subprocess.CalledProcessError as e:
        logging.debug(f"sips command failed: {e.stderr}")
        raise RuntimeError(f"Error running sips command: {e.stderr}")
    except FileNotFoundError:
        logging.debug("sips command not found")
        raise RuntimeError("sips command not found. This tool requires macOS.")
    except Exception as e:
        logging.debug(f"Unexpected error: {str(e)}")
        raise RuntimeError(f"Unexpected error converting HEIC: {str(e)}")
    finally:
        # Clean up temporary file
        if temp_jpeg.exists():
            logging.debug("Cleaning up temporary JPEG file")
            temp_jpeg.unlink()


def is_image_file(path: Path) -> bool:
    """Check if a file is an image file based on its extension."""
    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".heic", ".webp", ".tiff", ".tif"}
    return path.suffix.lower() in IMAGE_EXTS


def convert_to_supported_format(img: Image.Image, supported_mime_types: set[str]) -> bytes:
    """Convert image to a supported format for the model."""
    buffer = io.BytesIO()

    # Try formats in order of preference
    for format_name in ["JPEG", "PNG", "WEBP"]:
        mime_type = f"image/{format_name.lower()}"
        if mime_type in supported_mime_types:
            if format_name == "JPEG":
                # Convert to RGB for JPEG (removes alpha channel if present)
                if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                    img = img.convert("RGB")
            img.save(buffer, format=format_name)
            buffer.seek(0)
            return buffer.getvalue()

    # No supported format found
    logging.debug("supported_mime_types:", supported_mime_types)
    raise ValueError("No supported image format found")


def resize_image(img: Image.Image, max_long_side: int, max_short_side: int) -> Image.Image:
    """Resize image to fit within specified dimensions while maintaining aspect ratio.
    
    Args:
        img: PIL Image to resize
        max_long_side: Maximum length for the longest side
        max_short_side: Maximum length for the shortest side
    
    Returns:
        Resized PIL Image
    """
    width, height = img.size
    long_side, short_side = (width, height) if width >= height else (height, width)
    scale = min(max_long_side / long_side, max_short_side / short_side)
    if scale < 1:
        return img.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)
    return img
