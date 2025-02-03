#!/usr/bin/env python3


import asyncio
import logging
from pathlib import Path

import click

from .generators import get_model
from .rename_image_files import rename_image_files
from .types import CliOptions, RenameOptions


@click.command()
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.option("--all", "process_all", is_flag=True, help="Process all image files")
@click.option("-n", "--dry-run", is_flag=True, help="Show changes without renaming")
@click.option(
    "--add-dates",
    is_flag=True,
    help="Add dates from EXIF data if original filename has no date",
)
@click.option(
    "--allow-spaces/--no-spaces",
    "allow_spaces",
    default=True,
    help="Allow spaces in filenames",
)
@click.option(
    "--case",
    type=click.Choice(["upper", "lower", "sentence", "title", "infer"], case_sensitive=False),
    default="sentence",
    help="Case style for filenames (default: sentence)",
)
@click.option(
    "-j",
    "--jobs",
    type=click.IntRange(1, 20),
    default=10,
    help="Number of concurrent jobs (1-20, default: 10)",
)
@click.option(
    "--model",
    "model_name",
    type=click.STRING,
    default="gpt-4o-mini",
    help="Model to use for renaming (default: o1-mini)",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False),
    default="INFO",
    help="Set the logging level (default: INFO)",
)
def main(
    paths: list[str],
    process_all: bool,
    dry_run: bool,
    add_dates: bool,
    model_name: str | None,
    allow_spaces: bool | None,
    case: str | None,
    jobs: int,
    log_level: str,
) -> None:
    """Rename image files using AI-generated descriptions."""
    # Set up logging
    level = getattr(logging, log_level.upper())
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    # When not in debug mode, only show our own debug messages
    if level != logging.DEBUG:
        # Set third-party loggers to WARNING
        for logger_name in logging.root.manager.loggerDict:
            if not logger_name.startswith("rename_image_files"):
                logging.getLogger(logger_name).setLevel(logging.WARNING)

    model = get_model(model_name)
    rename_options = RenameOptions(
        add_dates=add_dates,
        allow_spaces=allow_spaces,
        case_style=case,
    )
    options = CliOptions(
        dry_run=dry_run,
        jobs=jobs,
        process_all=process_all,
        rename_options=rename_options,
    )

    # Convert paths to Path objects
    path_objects = [Path(p) for p in paths]

    # Run the async function
    asyncio.run(rename_image_files(path_objects, model=model, options=options))


if __name__ == "__main__":
    main()
