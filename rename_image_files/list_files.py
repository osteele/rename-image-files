from collections.abc import AsyncIterator
from pathlib import Path

import rich

from .cli import CliOptions
from .image_utils import is_image_file
from .utils import needs_rename


class EmptyDirectoryError(Exception):
    """Exception raised when a directory is empty."""

    def __init__(self, path: Path, ignored_files: list[Path]):
        self.path = path
        self.ignored_files = ignored_files
        super().__init__(f"Directory {path} is empty")


async def iter_image_files(
    files: list[Path],
    *,
    warn_on_invalid_files: bool = True,
    options: CliOptions,
) -> AsyncIterator[Path | EmptyDirectoryError]:
    """Iterate over image files in directory."""

    # Filter out non-image files and files that don't exist
    for file in files:
        if not file.exists():
            rich.print(f"[yellow]File not found: {file}[/yellow]")
            continue
        if file.is_dir():
            all_files = list(file.iterdir())
            all_files.sort()
            image_files = [f for f in all_files if is_image_file(f)]
            files_to_process = [f for f in image_files if options.process_all or needs_rename(f.name)]
            child_dirs = [f for f in all_files if f.is_dir()]
            found_image_file = bool(files_to_process)
            for file in files_to_process:
                yield file
            async for child in iter_image_files(child_dirs, warn_on_invalid_files=False, options=options):
                if isinstance(child, EmptyDirectoryError):
                    continue
                found_image_file = True
                yield child
            if not found_image_file:
                yield EmptyDirectoryError(file, image_files)
            continue
        if not is_image_file(file):
            if warn_on_invalid_files:
                rich.print(f"[yellow]Not an image file: {file}[/yellow]")
            continue
        if not options.process_all and not needs_rename(file.name):
            continue
        yield file
