from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    jira_email: str = ""
    jira_api_token: str = ""
    jira_base_url: str = "https://dataunveil.atlassian.net"
    host: str = "0.0.0.0"
    port: int = 8080
    auto_refresh_seconds: int = 30

    @property
    def credentials_configured(self) -> bool:
        return bool(self.jira_email.strip() and self.jira_api_token.strip())

    @property
    def jira_base_url_normalized(self) -> str:
        return self.jira_base_url.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
