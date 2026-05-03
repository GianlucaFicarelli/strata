from pydantic import BaseModel


class RegisterRequest(BaseModel):
    """Request body for user registration.

    Attributes:
        username: Desired username or email address.
        password: Plain-text password (hashed before storage).
    """

    username: str
    password: str


class TokenResponse(BaseModel):
    """Response body for a successful login.

    Attributes:
        access_token: Signed JWT access token.
        token_type: Always ``"bearer"``.
    """

    access_token: str
    token_type: str = "bearer"
