"""Application failures translated by the entry point into its own protocol."""


class ServiceError(Exception):
    """A failure the caller can act on. `payload` carries structured context,
    such as the receipt of a decision that already won a conflict."""

    def __init__(self, kind: str, message: str, payload: dict | None = None):
        super().__init__(message)
        self.kind = kind
        self.payload = payload
