from __future__ import annotations


class AppError(Exception):
    def __init__(self, message: str, *, code: str = "bad_request", status: int = 400, category: str = "request"):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.category = category


class InputError(AppError):
    def __init__(self, message: str, *, code: str = "bad_request"):
        super().__init__(message, code=code, status=400, category="input")


class ModelError(AppError):
    def __init__(self, message: str, *, code: str = "model_error"):
        super().__init__(message, code=code, status=500, category="model")


class MediaError(AppError):
    def __init__(self, message: str, *, code: str = "media_error", status: int = 400):
        super().__init__(message, code=code, status=status, category="media")


class TaskExecutionError(AppError):
    def __init__(self, message: str, *, code: str = "task_error", status: int = 500):
        super().__init__(message, code=code, status=status, category="task")


class StreamError(AppError):
    def __init__(self, message: str, *, code: str = "stream_error", status: int = 400):
        super().__init__(message, code=code, status=status, category="stream")


class ReportError(AppError):
    def __init__(self, message: str, *, code: str = "report_error", status: int = 500):
        super().__init__(message, code=code, status=status, category="report")
