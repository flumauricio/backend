from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str
    type: str
    role: str | None = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str
