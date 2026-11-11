from dataclasses import dataclass
from importlib.metadata import version

import pymupdf

from app.intake import validate_pdf


@dataclass(frozen=True)
class PDFInput:
    pages: tuple[str, ...]
    text: str
    path_version: str


def inspect_pdf(content: bytes, route: str = "text") -> PDFInput:
    validate_pdf(content)
    with pymupdf.open(stream=content, filetype="pdf") as doc:
        # Keep geometric text lines separate. sort=True can join two independent
        # columns into one row and destroy label/value association for verification.
        pages = tuple(
            "\n".join(
                "".join(span["text"] for span in line["spans"])
                for block in page.get_text("dict")["blocks"]
                if "lines" in block
                for line in block["lines"]
            )
            for page in doc
        )
        if route == "markdown":
            import pymupdf4llm

            text = pymupdf4llm.to_markdown(doc, show_progress=False)
            path_version = "pymupdf4llm-" + version("pymupdf4llm")
        elif route in ("text", "pdf"):
            text = "\n".join(f"PAGE {i + 1}\n{page}" for i, page in enumerate(pages))
            path_version = "pymupdf-" + version("pymupdf")
        else:
            raise ValueError("Input route must be text, markdown or pdf")
    if len(text) > 120000:
        raise ValueError("Local text exceeds bounded extraction input")
    return PDFInput(pages, text, path_version)
