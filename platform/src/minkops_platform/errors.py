"""Application failures translated by the entry point into its own protocol."""


class ServiceError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
