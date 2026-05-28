from fastapi import HTTPException, status


class AppException(HTTPException):
    """Base application exception."""

    def __init__(self, status_code: int, detail: str, headers: dict | None = None):
        super().__init__(status_code=status_code, detail=detail, headers=headers)


class CredentialsException(AppException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )


class PermissionDeniedException(AppException):
    def __init__(self, detail: str = "Permission denied.") -> None:
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class NotFoundException(AppException):
    def __init__(self, resource: str = "Resource") -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource} not found.",
        )


class ConflictException(AppException):
    def __init__(self, detail: str = "Resource already exists.") -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class BadRequestException(AppException):
    def __init__(self, detail: str = "Bad request.") -> None:
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class UnprocessableException(AppException):
    def __init__(self, detail: str) -> None:
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail
        )
