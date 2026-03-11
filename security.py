from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional

# --- Hashing Config ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- JWT Token Config ---
# This is a secret key. In a real app, this MUST be kept safe
# and not be in the code. We will generate a random one.
# You can generate your own by running `openssl rand -hex 32` in your terminal
SECRET_KEY = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30  # Tokens will be valid for 30 minutes


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compares a plain-text password with a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Takes a plain-text password and returns a secure hash."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """
    Creates a new JWT Access Token.

    The 'data' dictionary will be encoded into the token.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_current_user_email(token: str) -> Optional[str]:
    """
    Decodes a JWT token and returns the user's email (the 'sub' claim).

    Returns:
        The email string if the token is valid, otherwise None.
    """
    try:
        # Decode the token using our secret key
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # The email is stored in the 'sub' (subject) field
        email: str = payload.get("sub")
        if email is None:
            return None
        return email
    except JWTError:
        # If the token is invalid or expired, an error is raised
        return None