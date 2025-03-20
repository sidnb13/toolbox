import secrets
import string
from typing import Optional

from sqlalchemy.orm import Session

from logger import get_logger

from .models import ApiKey

logger = get_logger(__name__)


class AuthManager:
    def __init__(self, db_session: Session):
        self.db = db_session

    def create_api_key(self, instance_id: Optional[str] = None):
        """Create a new API key for an instance and store it in the database."""

        # Generate a random API key
        alphabet = string.ascii_letters + string.digits
        api_key = "".join(secrets.choice(alphabet) for _ in range(32))

        # Create new API key record
        new_key = ApiKey(
            key=api_key,
            instance_id=instance_id
            or "default",  # Use "default" if no instance_id provided
            is_active=True,
        )

        # Add and commit to database
        self.db.add(new_key)
        self.db.commit()

        return api_key

    def verify_agent_key(self, key: str) -> Optional[str]:
        """Verify an agent's API key, returns instance_id if valid"""
        try:
            api_key = (
                self.db.query(ApiKey)
                .filter(ApiKey.key == str(key), ApiKey.is_active == True)
                .first()
            )

            if not api_key:
                return None
            return api_key.instance_id
        except Exception as e:
            logger.error(f"Error verifying API key: {e}")
            return None
