import logging
from datetime import datetime

from rest_framework.views import exception_handler

logger = logging.getLogger("django")


def custom_exception_handler(exc, context):
    """
    Wraps DRF's default exception handler to return a consistent error shape:

    {
        "error": "ERROR_CODE",
        "message": "Human readable description",
        "timestamp": "2026-06-08T06:53:58Z"
    }

    Falls back to DRF default for any exception type not explicitly handled.
    """
    # Call DRF's default handler first to get the standard response
    response = exception_handler(exc, context)

    if response is not None:
        error_code = _get_error_code(response.status_code, response.data)
        message = _get_message(response.data)

        logger.warning(
            "API error response",
            extra={
                "error_code": error_code,
                "status_code": response.status_code,
                "error_message": message,
            },
        )

        response.data = {
            "error": error_code,
            "message": message,
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    return response


def _get_error_code(status_code: int, data: dict) -> str:
    """
    Maps HTTP status codes to error code strings.
    Checks for a pre-existing 'error' key first (set by views directly).
    """
    if isinstance(data, dict) and "error" in data:
        return data["error"]

    mapping = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        429: "TOO_MANY_REQUESTS",
        500: "INTERNAL_SERVER_ERROR",
    }
    return mapping.get(status_code, "ERROR")


def _get_message(data) -> str:
    """
    Extracts a human-readable message from DRF's error data.
    Handles all the shapes DRF produces:
      - {"detail": "..."}
      - {"field": ["error"]}
      - ["error string"]
      - plain string
    """
    if isinstance(data, dict):
        if "detail" in data:
            return str(data["detail"])
        if "message" in data:
            return str(data["message"])
        # Field-level validation errors — flatten to readable string
        messages = []
        for field, errors in data.items():
            if field in ("error", "timestamp"):
                continue
            if isinstance(errors, list):
                messages.append(f"{field}: {', '.join(str(e) for e in errors)}")
            else:
                messages.append(f"{field}: {errors}")
        return "; ".join(messages) if messages else "An error occurred"
    if isinstance(data, list):
        return "; ".join(str(e) for e in data)
    return str(data)
