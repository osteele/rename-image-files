import asyncio
import concurrent.futures
import io
import logging
import re
import signal
import sys
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import llm
import rich
from PIL import Image
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)

from .generators import generate_filename
from .image_utils import convert_heic_to_jpeg, convert_to_supported_format, resize_image
from .list_files import EmptyDirectoryError, iter_image_files
from .rate_limiter import RateLimiter
from .types import CliOptions, RenameOptions
from .utils import apply_case_style, read_exif_date, sanitize_filename

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif"}


@dataclass
class Stats:
    """Thread-safe statistics for directory scanning."""

    files_found: int = 0
    dirs_searched: int = 0

    def increment_files(self) -> None:
        """Increment files_found in a thread-safe way."""
        self.files_found += 1

    def increment_dirs(self) -> None:
        """Increment dirs_searched in a thread-safe way."""
        self.dirs_searched += 1


def process_filename(
    original: str,
    new_name: str,
    *,
    options: RenameOptions,
) -> str:
    """Process filename according to style options."""
    # Keep original extension
    ext = Path(original).suffix

    # Remove special characters and any existing extension
    base = re.sub(r"[^\w\s-]", "", Path(new_name).stem).strip()

    # Handle spaces vs hyphens
    if options.allow_spaces is None:
        # Infer from original
        allow_spaces = any(c.isspace() for c in original)
    else:
        allow_spaces = options.allow_spaces

    # Handle case
    if options.case_style is None:
        # Infer from original: if all lowercase, make new name lowercase
        if not any(c.isupper() for c in original):
            base = base.lower()
    else:
        base = apply_case_style(base, options.case_style)

    base = sanitize_filename(
        base,
        allow_accents=True,
        allow_punctuation=True,
        allow_spaces=allow_spaces,
        allow_uppercase=True,  # handled by apply_case_style
        require_ascii=False,
    )

    return f"{base}{ext}"


def get_image_date(image_path: str) -> str | None:
    """Extract date from image EXIF data or filename."""
    date = read_exif_date(image_path)
    if date:
        return date.strftime("%Y-%m-%d")
    return None


# Global flag to track cancellation status
is_cancelled = False


def handle_sigint(signum, frame):
    """Handle Ctrl+C by setting the cancellation flag."""
    global is_cancelled
    is_cancelled = True
    print("\nCancelling remaining tasks...")


def process_image(
    image_path: Path,
    model: llm.Model,
    options: CliOptions,
    progress: Progress,
    task_id: TaskID,
    rate_limiter: RateLimiter,
    loop: asyncio.AbstractEventLoop,
    executor: concurrent.futures.ThreadPoolExecutor,
) -> tuple[Path, str]:
    """Process a single image."""
    rename_options = options.rename_options
    add_dates = rename_options.add_dates
    supported_image_types = model.attachment_types

    # Image resize parameters
    max_long_side = 2048
    max_short_side = 768

    try:
        logging.debug(f"Starting to process {image_path}")

        # Handle HEIC files specially
        if image_path.suffix.lower() == ".heic":
            try:
                logging.debug("Converting HEIC to JPEG")
                # Convert HEIC to JPEG first
                binary_content = convert_heic_to_jpeg(image_path)
                logging.debug("HEIC conversion successful")

                logging.debug("Opening converted JPEG with PIL")
                # Create a PIL Image from the JPEG data
                img = Image.open(io.BytesIO(binary_content))
                logging.debug("Successfully opened with PIL")
            except Exception as e:
                if not is_cancelled:  # Only show warnings if not cancelled
                    progress.console.print(f"[yellow]Warning: Error processing {image_path}: {str(e)}")
                    import traceback

                    progress.console.print("[red]Full error:")
                    progress.console.print(traceback.format_exc())
                raise

            logging.debug("Getting EXIF date")
            exif_date = get_image_date(str(image_path)) if add_dates else None
            logging.debug(f"EXIF date: {exif_date}")

            logging.debug("Resizing image")
            img = resize_image(img, max_long_side, max_short_side)
            logging.debug("Converting to supported format")
            binary_content = convert_to_supported_format(img, supported_image_types)
        else:
            logging.debug("Processing non-HEIC image")
            # Handle other image formats
            with Image.open(image_path) as img:
                exif_date = get_image_date(str(image_path)) if add_dates else None
                img = resize_image(img, max_long_side, max_short_side)
                binary_content = convert_to_supported_format(img, supported_image_types)

        logging.debug("Waiting for rate limiter before making request")
        future = asyncio.run_coroutine_threadsafe(rate_limiter.before_request(), loop)
        future.result()

        try:
            logging.debug("Making request to generate filename")
            # Use the executor to run the model.prompt call
            future = executor.submit(
                generate_filename,
                model,
                image_content=binary_content,
            )
            response = future.result(timeout=30)  # 30 second timeout
            logging.debug("Received response from filename generation")
            # Mark success to reset backoff
            future = asyncio.run_coroutine_threadsafe(rate_limiter.on_success(), loop)
            future.result()
        except Exception as e:
            if "Resource has been exhausted" in str(e):
                # Update backoff and show info in progress
                future = asyncio.run_coroutine_threadsafe(rate_limiter.on_rate_limit(), loop)
                backoff = future.result()
                if not is_cancelled:
                    progress.update(
                        task_id,
                        description=f"[yellow]Rate limited, waiting {backoff:.1f}s...",
                    )
            raise

        generated_name = response

        logging.debug("Stripping leading date from generated name")
        # Strip any leading date from the generated name
        generated_name = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", generated_name)
        clean_name = process_filename(image_path.name, generated_name, options=rename_options)

        logging.debug("Handling dates")
        # Handle dates
        date_part = exif_date if rename_options.add_dates else None
        if date_from_name := get_image_date(str(image_path)):
            # Use date from original filename if present
            date_part = date_from_name

        logging.debug("Combining date and name")
        # Combine date and name
        separator = (
            " "
            if (rename_options.allow_spaces or (rename_options.allow_spaces is None and " " in image_path.name))
            else "-"
        )
        new_stem = f"{date_part}{separator}{clean_name}" if date_part else clean_name
        new_name = process_filename(image_path.name, new_stem, options=rename_options)

        logging.debug("Renaming file")
        # Rename file
        new_path = image_path.with_name(new_name)
        if not options.dry_run:
            image_path.rename(new_path)

        progress.update(task_id, completed=1)
        return image_path, new_name
    except Exception as e:
        progress.update(task_id, completed=1, description=f"[red]Failed {image_path.name}")
        raise e


async def process_with_progress(
    file_path: Path,
    *,
    options: CliOptions,
    model: llm.Model,
    progress: Progress,
    task_semaphore: asyncio.BoundedSemaphore,
    rate_limiter: RateLimiter,
    executor: concurrent.futures.ThreadPoolExecutor,
) -> tuple[Path, str]:
    """Process a single image."""
    async with task_semaphore:
        if is_cancelled:
            return file_path, ""  # Return early if cancelled
        task_id = progress.add_task(f"Processing {file_path.name}...", total=1, start=False)
        try:
            progress.start_task(task_id)
            result = await asyncio.to_thread(
                process_image,
                file_path,
                model,
                options,
                progress,
                task_id,
                rate_limiter,
                asyncio.get_event_loop(),
                executor,
            )
            if not is_cancelled:  # Only show progress if not cancelled
                progress.console.print(
                    f"{'Would rename' if options.dry_run else 'Renamed'} " f"{file_path.name} → {result[1]}"
                )
            progress.update(task_id, visible=False)
            return result
        except Exception as e:
            if not is_cancelled:  # Only show errors if not cancelled
                if "Resource has been exhausted" not in str(e):
                    progress.console.print(f"[red]Error processing {file_path}: {e}")
            progress.update(task_id, visible=False)
            raise e


async def process_batch(
    files: AsyncIterator[Path | EmptyDirectoryError],
    *,
    model: llm.Model,
    options: CliOptions,
    progress: Progress,
    task_semaphore: asyncio.BoundedSemaphore,
    rate_limiter: RateLimiter,
    executor: concurrent.futures.ThreadPoolExecutor,
) -> AsyncIterator[tuple[Path, str] | Exception]:
    """Process a batch of files with limited concurrency."""
    active_tasks = []

    # Create tasks for all files
    async for path_or_exception in files:
        if isinstance(path_or_exception, EmptyDirectoryError):
            yield path_or_exception
            continue
        if len(active_tasks) >= options.jobs:  # Limit concurrent tasks
            done, pending = await asyncio.wait(active_tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                try:
                    yield await task
                except Exception as e:
                    yield e
            active_tasks = list(pending)

        task = asyncio.create_task(
            process_with_progress(
                path_or_exception,
                model=model,
                options=options,
                progress=progress,
                task_semaphore=task_semaphore,
                rate_limiter=rate_limiter,
                executor=executor,
            )
        )
        active_tasks.append(task)

    # Wait for remaining tasks
    if active_tasks:
        done, _ = await asyncio.wait(active_tasks)
        for task in done:
            try:
                yield await task
            except Exception as e:
                yield e


async def rename_image_files(
    files: list[Path],
    *,
    model: llm.Model,
    options: CliOptions,
) -> None:
    """Rename image files using LLM-generated descriptions.

    Args:
        files: List of image files to process
        model: LLM model to use for generating descriptions
        options: Command-line options
    """
    if not files:
        rich.print("[yellow]No files to process[/yellow]")
        return

    # TODO: do this in enough process so that we can front-run the generation,
    # and show the remaining file count when it reaches the end
    files_to_process = iter_image_files(files, options=options)

    # TODO: add this back
    # if not files_to_process:
    #     rich.print("[yellow]No valid image files to process[/yellow]")
    #     return

    # Set up progress bar
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        transient=True,
    )
    # TODO: show remaining files when the generator concludes
    progress.add_task("Processing files...")  # total=len(files_to_process))

    # Set up concurrency control
    task_semaphore = asyncio.BoundedSemaphore(options.jobs)
    rate_limiter = RateLimiter()

    # Handle SIGINT gracefully
    is_cancelled = False

    def sigint_handler(signum, frame):
        nonlocal is_cancelled
        if is_cancelled:
            sys.exit(1)
        is_cancelled = True
        rich.print("\n[yellow]Cancelling... Press Ctrl+C again to force quit[/yellow]")

    original_sigint_handler = signal.signal(signal.SIGINT, sigint_handler)

    empty_directory_errors = []
    try:
        # Process files with limited concurrency
        with progress:
            successful = 0
            failed = 0

            async for result in process_batch(
                files_to_process,
                model=model,
                options=options,
                progress=progress,
                task_semaphore=task_semaphore,
                rate_limiter=rate_limiter,
                executor=concurrent.futures.ThreadPoolExecutor(max_workers=options.jobs),
            ):
                if isinstance(result, EmptyDirectoryError):
                    empty_directory_errors.append(result)
                elif isinstance(result, Exception):
                    failed += 1
                else:
                    successful += 1

            if not is_cancelled:
                rich.print(f"\nProcessed {successful} files successfully, {failed} failed")

        skipped_file_count = 0
        for error in empty_directory_errors:
            rich.print(f"[yellow]Directory {error.path} is empty[/yellow]")
            if error.ignored_files:
                rich.print("  [yellow]Ignored files:[/yellow]")
                rich.print(", ".join(f"[yellow]{file}[/yellow]" for file in error.ignored_files[:10]))
                if len(error.ignored_files) > 10:
                    rich.print("    [yellow]... and more[/yellow]")
                skipped_file_count += len(error.ignored_files)

        if skipped_file_count > 0:
            rich.print("[yellow]Run with --all to process these files[/yellow]")
    finally:
        signal.signal(signal.SIGINT, original_sigint_handler)
