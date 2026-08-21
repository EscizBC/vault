"""Application configuration loaded from environment variables (.env)."""

import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)


class Settings(BaseSettings):
    """Application settings.

    Values are read from environment variables or the ``.env`` file.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = "8576991670:AAHxd0XwGPGIwGTnfW-TiiH5JUXtEtlYsI4"
    admin_ids: str = "6380771602"  # comma-separated Telegram user IDs
    webapp_url: str = "http://localhost:3000"
    database_url: str = "sqlite+aiosqlite:///./shop.db"

    # CryptoBot (Crypto Pay API, https://help.crypt.bot/crypto-pay-api)
    cryptobot_token: str = "624387:AAu9815wjY3voyqfoANKzCOyxzN1v1bJBJx"
    cryptobot_api_url: str = "https://pay.crypt.bot/api"

    @property
    def admin_id_list(self) -> list[int]:
        """Return admin IDs parsed from the comma-separated string."""
        return [int(x) for x in self.admin_ids.split(",") if x.strip().isdigit()]

    def model_post_init(self, __context: object) -> None:
        """Normalize the Web App URL (strip whitespace, quotes and trailing slash)."""
        self.webapp_url = self.webapp_url.strip().strip('"').strip("'").rstrip("/")


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()


settings: Settings = get_settings()
