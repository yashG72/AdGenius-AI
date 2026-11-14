"""Document ingestion: validate -> extract -> clean -> chunk -> embed -> index.

Each step is a small module with plain functions so it can be tested on its own.
`pipeline.py` wires them together and manages the document's status.
"""


class IngestionError(Exception):
    """A permanent problem with the document itself (retrying will not help)."""
