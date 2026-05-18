from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_key: str | None = None
    max_domains_per_request: int = 50
    request_timeout_seconds: float = 12.0
    max_concurrent_checks: int = 10
    rdap_bootstrap_url: str = "https://data.iana.org/rdap/dns.json"
    host: str = "0.0.0.0"
    port: int = 8585


settings = Settings()
