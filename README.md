# rename-image-files

A command-line tool that uses vision language models to intelligently rename image files based on their content.

## Features

- Uses vision language models (default: gpt-4o-mini) to generate descriptive filenames
- Extracts and preserves dates from EXIF metadata and filenames (format: YYYY-MM-DD)
- Supports multiple models for comparison
- Customizable prompts for different naming styles
- Dry-run mode to preview changes
- Clean, filename-safe output with hyphens and lowercase letters
- Smart filtering to only process camera-generated files by default
- Recursive directory traversal (skips dot directories)

## Installation

Run or install with uv:

```bash
uv tool install https://github.com/osteele/rename-image-files.git
```

Or pip:

```bash
pip install git+https://github.com/osteele/rename-image-files.git
```

## Configuration

Set your OpenAI API key as an environment variable if using OpenAI models:

```bash
export OPENAI_API_KEY=your-api-key-here
```

You can get an API key from [OpenAI's platform](https://platform.openai.com/api-keys).

## Usage

Basic usage:

```bash
rename-image-files image1.jpg image2.jpg
```

By default, the tool only processes files whose names:
- Start with 'IMG-' or 'IMG_' (case-insensitive)
- Look like UUIDs (e.g., 63C0900B-4465-4CF9-A310-327C627DB9EA)

Example output:
```
IMG_1234.JPG → 2024-01-01-sunset-over-golden-gate-bridge.jpg
IMG_5678.jpeg → 2024-01-01-two-cats-playing-with-red-yarn.jpg
```

To process all image files:

```bash
rename-image-files --all image1.jpg image2.jpg
```

Compare different models:

```bash
rename-image-files --model gpt-4o-mini --model gpt-4-vision-preview image.jpg
```

Use a custom prompt:

```bash
rename-image-files --prompt "Describe this image in 3-5 words" image.jpg
```

Preview changes without renaming:

```bash
rename-image-files --dry-run image.jpg
```

Compare different prompts:

```bash
rename-image-files \
  --prompt "Describe this image in 3-5 words" \
  --prompt "What's the main subject of this image?" \
  image.jpg
```

Process a directory:

```bash
# Process files in directory (non-recursive)
rename-image-files ~/Pictures/Vacation

# Process files in directory and all subdirectories (skips dot directories)
rename-image-files -r ~/Pictures/Vacation
```

## Development

### Prerequisites

- Python 3.12 or later
- [uv](https://github.com/astral-sh/uv) for dependency management
- [just](https://github.com/casey/just) for running development commands

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/osteele/rename-image-files.git
   cd rename-image-files
   ```

2. Install development dependencies:
   ```bash
   just setup
   ```

### Development Commands

- `just check` - Run linting, formatting, and tests
- `just format` - Format code
- `just fix` - Fix linting and formatting issues (works in dirty git workspaces)
- `just test` - Run tests
- `just test-cov` - Run tests with coverage report

## License

MIT License. See [LICENSE](LICENSE) for details.

## Author

Oliver Steele