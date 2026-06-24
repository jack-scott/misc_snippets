from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    st_api_key: str = "server-api-key-fleetserver01"
    st_base_url: str = "http://127.0.0.1:8384"
    local_subnet: str = "172.0.0.0/8"
    keys_dir: Path = Path("keys")
    tunnel_port_start: int = 9384
    ssh_key_path: str = "docker/keys/test_key"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="FLEET_", extra="ignore")


settings = Settings()
