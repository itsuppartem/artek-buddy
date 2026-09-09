from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PLACEHOLDER_TOKENS = {"change-me", "changeme", "secret", "token", "password"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    cursor_api_key: str = ""
    agent_http_token: str

    @field_validator("agent_http_token")
    @classmethod
    def reject_placeholder_host_token(cls, value: str) -> str:
        token = (value or "").strip()
        if not token or token.lower() in _PLACEHOLDER_TOKENS:
            raise ValueError("AGENT_HTTP_TOKEN is missing or still a placeholder")
        return token

    agent_runtime: str = "cursor"
    cursor_model: str = "grok-4.6"
    cursor_model_effort: str = "xhigh"
    cursor_model_fast: bool = True
    cursor_unary_timeout_s: float = 60.0
    cursor_stream_timeout_s: float = 600.0
    cursor_max_retries: int = 1
    composio_api_key: str = ""
    connections_callback_url: str = "https://host.example/v1/connections/callback"
    agent_cwd: str = "/workspace"
    agent_data_dir: str = "/data"
    http_host: str = "0.0.0.0"
    http_port: int = 8080
    web_root: str = ""
    database_url: str = "postgresql://artek:artek@127.0.0.1:5432/artek_buddy"
    sandbox_supervisor_url: str = "http://127.0.0.1:7091"
    sandbox_supervisor_token: str = ""
    sandbox_provider: str = "docker"
    computer_image: str = "artek-buddy-computer:local"
    computer_idle_seconds: int = 900
    computer_takeover_idle_seconds: int = 120
    computer_takeover_ttl_seconds: int = 900
    memory_gateway_url: str = "http://127.0.0.1:8420"
    credential_broker_url: str = "http://127.0.0.1:8431"
    credential_broker_token: str = ""
    consent_auto: str = ""
    log_format: str = ""

    @field_validator("cursor_unary_timeout_s", "cursor_stream_timeout_s")
    @classmethod
    def require_positive_cursor_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("must be greater than 0")
        return value

    @field_validator("cursor_max_retries")
    @classmethod
    def require_nonnegative_cursor_retries(cls, value: int) -> int:
        if value < 0:
            raise ValueError("must be 0 or greater")
        return value


def get_settings() -> Settings:
    return Settings()
