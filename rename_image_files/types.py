from dataclasses import dataclass


@dataclass
class RenameOptions:
    """Options for renaming files."""

    add_dates: bool
    allow_spaces: bool | None  # None means infer from original
    case_style: str | None  # None means infer from original


@dataclass
class CliOptions:
    dry_run: bool
    process_all: bool
    rename_options: RenameOptions
    jobs: int
