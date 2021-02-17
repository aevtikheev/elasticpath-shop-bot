"""Settings for Elasticpath Shop Bot."""
from dataclasses import dataclass

from environs import Env


@dataclass(frozen=True)
class Settings:
    """Settings for Elasticpath Shop Bot."""

    tg_bot_token: str
    elasticpath_client_id: str
    elasticpath_client_secret: str
    redis_host: str
    redis_port: int
    redis_password: str


def get_settings() -> Settings:
    """Read environment settings."""
    env = Env()
    env.read_env()
    return Settings(
        tg_bot_token=env('TELEGRAM_BOT_TOKEN', None),
        elasticpath_client_id=env('ELASTICPATH_CLIENT_ID', None),
        elasticpath_client_secret=env('ELASTICPATH_CLIENT_SECRET', None),
        redis_host=env('REDIS_HOST', None),
        redis_port=env.int('REDIS_PORT', None),
        redis_password=env('REDIS_PASSWORD', None),
    )


settings = get_settings()
