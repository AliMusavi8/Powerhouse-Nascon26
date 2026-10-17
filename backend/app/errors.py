"""Standard error envelope (spec 5.2) and helpers for the Appendix B catalogue."""


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str = "", details: dict | None = None,
                 headers: dict | None = None):
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message or code.replace("_", " ").capitalize()
        self.details = details or {}
        self.headers = headers

    def body(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


def validation(fields, message: str = "Request validation failed.") -> ApiError:
    if isinstance(fields, str):
        fields = [fields]
    return ApiError(400, "VALIDATION_ERROR", message, {"fields": list(dict.fromkeys(fields))})


def not_found(code: str, message: str, **details) -> ApiError:
    return ApiError(404, code, message, details)


def conflict(code: str, message: str, **details) -> ApiError:
    return ApiError(409, code, message, details)
