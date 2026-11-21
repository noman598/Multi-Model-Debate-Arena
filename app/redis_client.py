from datetime import datetime, timezone
import json
import logging
from typing import Any, Optional
import redis
from fakeredis import FakeRedis

from app.config import settings

logger = logging.getLogger("auth.redis")


class RedisTokenStore:
    """
    Manages refresh token storage and lifecycle using Redis.
    Uses real Redis when configured and reachable, with automatic
    in-memory FakeRedis fallback for seamless local development and testing.
    """

    def __init__(self, redis_url: str = settings.REDIS_URL, use_real: bool = settings.USE_REAL_REDIS):
        self.redis_url = redis_url
        self.use_real = use_real
        self.client: Any = None
        self.is_fallback: bool = True

    def connect(self) -> None:
        """Initializes the Redis client."""
        if self.use_real:
            try:
                real_client = redis.Redis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=1.0,
                    socket_timeout=1.0
                )
                real_client.ping()
                self.client = real_client
                self.is_fallback = False
                logger.info("Connected to real Redis at %s", self.redis_url)
                return
            except Exception as exc:
                logger.warning(
                    "Could not connect to Redis at %s (%s). Falling back to in-memory store.",
                    self.redis_url,
                    exc
                )

        # In-memory Redis store (fakeredis)
        self.client = FakeRedis(decode_responses=True)
        self.is_fallback = True
        logger.info("Using in-memory Redis token store (fakeredis).")

    def ping(self) -> bool:
        if self.client is None:
            self.connect()
        try:
            return bool(self.client.ping())
        except Exception:
            return False

    def store_refresh_token(
        self,
        token: str,
        user_id: int,
        username: str,
        ttl_seconds: int
    ) -> None:
        """
        Stores a refresh token with user payload and expiration TTL.
        Also registers the token in user's active tokens set.
        """
        if self.client is None:
            self.connect()

        payload = {
            "user_id": user_id,
            "username": username,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        token_key = f"refresh_token:{token}"
        user_tokens_key = f"user_tokens:{user_id}"

        # Store token data with expiration
        self.client.setex(token_key, ttl_seconds, json.dumps(payload))
        # Keep track of active tokens for the user
        self.client.sadd(user_tokens_key, token)
        self.client.expire(user_tokens_key, ttl_seconds + 86400)

    def get_refresh_token(self, token: str) -> Optional[dict]:
        """Retrieves and parses the payload for a given refresh token."""
        if self.client is None:
            self.connect()

        token_key = f"refresh_token:{token}"
        raw_data = self.client.get(token_key)
        if not raw_data:
            return None
        try:
            return json.loads(raw_data)
        except json.JSONDecodeError:
            return None

    def delete_refresh_token(self, token: str) -> bool:
        """Deletes a refresh token from Redis and removes it from user's active set."""
        if self.client is None:
            self.connect()

        data = self.get_refresh_token(token)
        token_key = f"refresh_token:{token}"
        deleted = self.client.delete(token_key)

        if data and "user_id" in data:
            user_tokens_key = f"user_tokens:{data['user_id']}"
            self.client.srem(user_tokens_key, token)

        return deleted > 0

    def revoke_all_user_tokens(self, user_id: int) -> int:
        """Revokes all active refresh tokens for a specific user."""
        if self.client is None:
            self.connect()

        user_tokens_key = f"user_tokens:{user_id}"
        tokens = self.client.smembers(user_tokens_key)
        count = 0
        for token in tokens:
            self.client.delete(f"refresh_token:{token}")
            count += 1
        self.client.delete(user_tokens_key)
        return count

    def close(self) -> None:
        """Closes the Redis connection."""
        if self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass


# Global singleton instance
redis_store = RedisTokenStore()
