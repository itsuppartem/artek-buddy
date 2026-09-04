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


def get_settings() -> Settings:
    return Settings()
