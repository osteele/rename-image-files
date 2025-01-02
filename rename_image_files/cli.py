#!/usr/bin/env python3

import os
import queue
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from threading import Event, Thread
from typing import Generator, NamedTuple

import click
import llm

from .utils import get_exif_date, is_camera_filename, sanitize_filename

DEFAULT_PROMPT = """You are a helpful assistant that names image files.
Describe this image in a concise way that would make a good filename.
Focus on the main subject and key details.
Keep it brief but descriptive.
Example descriptions:
- Sunset over Golden Gate Bridge
- Two Cats Playing with Red Yarn
- Mountain Lake Reflecting Snow Peaks
- Child Blowing Birthday Candles"""

MAX_RETRIES = 3  # Number of times to retry generating a shorter name
MAX_FILENAME_LENGTH = 255  # Maximum filename length on most filesystems


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


@dataclass
class SkippedFile:
    """Information about a skipped file."""
    path: Path
    reason: str


class ScanResult(NamedTuple):
    """Result of scanning a single file."""
    path: Path
    stats: Stats


def generate_filename(
    model: llm.Model,
    image_path: str,
    prompt: str = DEFAULT_PROMPT,
) -> str:
    """Generate a filename using the vision language model."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise click.ClickException(
            "OPENAI_API_KEY environment variable not set. "
            "Get one from https://platform.openai.com/api-keys"
        )

    response = model.prompt(
        prompt,
        attachments=[llm.Attachment(path=image_path)],
    )

    return sanitize_filename(response.text())


def scan_directory(
    path: Path,
    recursive: bool,
    queue: Queue[ScanResult | None],
    stats: Stats,
    done: Event,
) -> None:
    """Scan directory for image files in a separate thread."""
    try:
        if path.is_file():
            if path.suffix.lower() in [".jpg", ".jpeg", ".png", ".gif"]:
                stats.increment_files()
                queue.put(ScanResult(path, stats))
            done.set()
            return

        def scan_dir(dir_path: Path) -> None:
            try:
                # Count this directory before scanning it
                stats.increment_dirs()
                items = list(dir_path.iterdir())
            except PermissionError:
                click.echo(f"Skipping {dir_path}: Permission denied", err=True)
                return

            # First process all files in this directory
            for item in items:
                if done.is_set():  # Check for early termination
                    return
                if item.is_file() and item.suffix.lower() in [".jpg", ".jpeg", ".png", ".gif"]:
                    stats.increment_files()
                    queue.put(ScanResult(item, stats))

            # Then process subdirectories
            if recursive:
                for item in items:
                    if done.is_set():  # Check for early termination
                        return
                    if item.is_dir() and not item.name.startswith("."):
                        scan_dir(item)

        # Start scanning
        scan_dir(path)
    finally:
        # Always signal completion, even if there's an error
        done.set()
        queue.put(None)  # Sentinel value


@click.command()
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option(
    "--model",
    "-m",
    multiple=True,
    default=["gpt-4o-mini"],
    help="Model to use for image description. Can be specified multiple times.",
)
@click.option(
    "--prompt",
    "-p",
    multiple=True,
    help="Custom prompt to use. Can be specified multiple times.",
)
@click.option(
    "--dry-run",
    "-n",
    is_flag=True,
    help="Print changes without renaming files",
)
@click.option(
    "--all",
    "-a",
    "process_all",
    is_flag=True,
    help="Process all image files, not just those with camera-style names",
)
@click.option(
    "--recursive",
    "-r",
    is_flag=True,
    help="Recursively process subdirectories (skips dot directories)",
)
def main(
    files: tuple[str, ...],
    model: tuple[str, ...],
    prompt: tuple[str, ...],
    dry_run: bool,
    process_all: bool,
    recursive: bool,
) -> None:
    """Rename image files based on their content using vision language models."""
    if not prompt:
        prompt = (DEFAULT_PROMPT,)

    # Load all models
    models = {name: llm.get_model(name) for name in model}

    # Process each file or directory
    processed_files = False
    skipped_files = False
    skipped_list: list[SkippedFile] = []

    for file_path in files:
        # Set up thread communication
        path = Path(file_path)
        file_queue: Queue[ScanResult | None] = Queue()
        stats = Stats()
        done = Event()

        # Start scanner thread
        scanner = Thread(
            target=scan_directory,
            args=(path, recursive, file_queue, stats, done),
            daemon=True,
        )
        scanner.start()

        # Process files as they're found
        while not (done.is_set() and file_queue.empty()):
            try:
                # Wait up to 1 second for a new file
                result = file_queue.get(timeout=1.0)
                if result is None:  # Sentinel value
                    continue

                img_path = result.path
                current_stats = result.stats

                # Check filename pattern
                if not process_all and not is_camera_filename(img_path.name):
                    skipped_files = True
                    continue

                processed_files = True

                # Get the date from EXIF data or filename
                date_prefix = ""
                date = get_exif_date(str(img_path))
                if date:
                    date_prefix = date.strftime("%Y-%m-%d-")

                # Try generating filenames with retries for long names
                success = False
                for attempt in range(MAX_RETRIES):
                    # Add "brief" to the prompt after first attempt
                    current_prompt = prompt[0]
                    if attempt > 0:
                        current_prompt = "Keep it very brief. " + current_prompt

                    # Generate filenames using each model/prompt combination
                    results = []
                    for model_name, model_obj in models.items():
                        for p in prompt:
                            new_name = generate_filename(model_obj, str(img_path), p)
                            full_name = f"{date_prefix}{new_name}{img_path.suffix.lower()}"
                            if len(full_name) <= MAX_FILENAME_LENGTH:
                                results.append((model_name, p, full_name))
                                success = True
                                break
                        if success:
                            break
                    if success:
                        break

                if not success:
                    # All attempts produced too-long filenames
                    skipped_list.append(
                        SkippedFile(img_path, "Generated filename too long")
                    )
                    continue

                # Display results
                if len(results) == 1:
                    # Single model and prompt - use compact format
                    new_name = results[0][2]
                    action = "Would rename" if dry_run else "Rename"
                    click.echo(f"{action} {img_path} → {new_name}")
                else:
                    # Multiple models or prompts - show detailed format
                    click.echo(f"\nResults for {img_path}:")
                    for model_name, p, new_name in results:
                        if len(models) > 1:
                            click.echo(f"  Model: {model_name}")
                        if len(prompt) > 1:
                            click.echo(f"  Prompt: {p[:50]}...")
                        click.echo(f"  → {new_name}")

                # If not dry run and we have exactly one result, perform the rename
                if not dry_run and len(results) == 1:
                    new_path = img_path.parent / results[0][2]
                    try:
                        if new_path.exists():
                            skipped_list.append(
                                SkippedFile(img_path, f"Target {new_path} exists")
                            )
                            continue
                        img_path.rename(new_path)
                    except OSError as e:
                        skipped_list.append(SkippedFile(img_path, str(e)))
                        continue

            except queue.Empty:
                # Show progress on timeout if we're still scanning
                if not done.is_set():
                    click.echo(
                        f"Scanning... Found {stats.files_found} images in "
                        f"{stats.dirs_searched} directories",
                        err=True,
                    )

        # Wait for scanner thread to finish
        scanner.join()

        # Print final summary for this path
        if recursive and (stats.files_found > 0 or stats.dirs_searched > 0):
            click.echo(
                f"\nScanned {stats.dirs_searched} directories, "
                f"found {stats.files_found} images",
                err=True,
            )

    # Print warning if we skipped files but didn't process any
    if skipped_files and not processed_files:
        click.echo(
            "\nWarning: No files were processed because none matched the default "
            "filename patterns (IMG-*, IMG_*, or UUID-style names).",
            err=True,
        )
        click.echo(
            "To process all image files, use the --all option.",
            err=True,
        )

    # Print summary of skipped files
    if skipped_list:
        click.echo("\nSkipped files:", err=True)
        for skipped in skipped_list:
            click.echo(f"  {skipped.path}: {skipped.reason}", err=True)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
