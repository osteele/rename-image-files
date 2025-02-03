import os

import click
import llm

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

# Initialize the model once, outside of the processing function
# model = llm.get_model("gemini-2.0-flash-exp")


def get_model(model_name: str | None) -> llm.Model:
    model = llm.get_model(model_name or "o1-mini")
    if not model.key:
        if not os.environ.get("OPENAI_API_KEY"):
            raise click.ClickException(
                "OPENAI_API_KEY environment variable not set. " "Get one from https://platform.openai.com/api-keys"
            )
        # TODO: conditionalize this based on model_name
        # model.key = os.getenv("OPENAI_API_KEY")
    if not any(t in model.attachment_types for t in ["image/jpeg", "image/png", "image/webp"]):
        raise click.ClickException(f"Model {model_name} does not support any image types")
    return model


def generate_filename(model: llm.Model, image_content: bytes) -> str:
    return model.prompt(
        DEFAULT_PROMPT,
        attachments=[llm.Attachment(content=image_content)],
    ).text()
