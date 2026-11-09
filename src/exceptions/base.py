class AppException(Exception):
    """
    Base class for app exceptions.
    """

    status_code = 500
    detail = "An unexpected error occurred."

    def __init__(self, detail: str | None = None):
        self.detail = detail if detail is not None else self.detail
        super().__init__(self.detail)