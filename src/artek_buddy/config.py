from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    cursor_api_key: str = ""
    agent_http_token: str
    agent_runtime: str = "cursor"
    cursor_model: str = "grok-4.6"
    cursor_model_effort: str = "xhigh"
    cursor_model_fast: bool = True
    agent_cwd: str = "/workspace"
    agent_data_dir: str = "/data"
    http_host: str = "0.0.0.0"
    http_port: int = 8080
    database_url: str = "postgresql://artek:artek@127.0.0.1:5432/artek_buddy"
    sandbox_supervisor_url: str = "http://127.0.0.1:7091"
    sandbox_supervisor_token: str = ""
    sandbox_provider: str = "docker"
    computer_image: str = "artek-buddy-computer:local"
    computer_idle_seconds: int = 600
    computer_takeover_ttl_seconds: int = 900


def get_settings() -> Settings:
    return Settings()
