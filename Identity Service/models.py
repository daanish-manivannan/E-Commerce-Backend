from typing import TYPE_CHECKING

from database import Base
from sqlalchemy import Boolean, Column, DateTime, Integer, String

if TYPE_CHECKING:
    from typing import Any

    # Type checking declarations for mypy
    class User(Base):
        id: Any
        email: Any
        hashed_password: Any
        is_active: Any
        refresh_token: Any
        refresh_token_expiry: Any
        email_verified: Any
        email_verification_token: Any
        email_verification_expiry: Any
        password_reset_token: Any
        password_reset_expiry: Any

else:
    # Runtime declarations for SQLAlchemy
    class User(Base):
        __tablename__ = "identity_users"

        id = Column(Integer, primary_key=True, index=True)
        email = Column(String, unique=True, index=True, nullable=False)
        hashed_password = Column(String, nullable=False)
        is_active = Column(Boolean, default=True)
        refresh_token = Column(String, unique=True, index=True, nullable=True)
        refresh_token_expiry = Column(DateTime, nullable=True)
        email_verified = Column(Boolean, default=False)
        email_verification_token = Column(
            String, unique=True, index=True, nullable=True
        )

        email_verification_expiry = Column(DateTime, nullable=True)
        password_reset_token = Column(String, unique=True, index=True, nullable=True)
        password_reset_expiry = Column(DateTime, nullable=True)
