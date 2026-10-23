"""Platform failures as HTTP answers: one translation for every route."""

from fastapi import HTTPException

from minkops_platform.errors import ServiceError

STATUS = {"invalid": 422, "unauthorized": 401, "forbidden": 403, "not_found": 404, "conflict": 409}


def call(action, *args, **kwargs):
    try:
        return action(*args, **kwargs)
    except ServiceError as error:
        # Structured context (such as the receipt that won a conflict) travels
        # with the message so the client can show the authoritative outcome.
        detail = {"message": str(error), **error.payload} if error.payload else str(error)
        raise HTTPException(STATUS[error.kind], detail) from error
