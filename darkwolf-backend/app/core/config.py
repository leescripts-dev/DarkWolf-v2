from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DarkWolf Backend"
    app_env: str = "development"
    debug: bool = True

    mongo_uri: str = "mongodb://127.0.0.1:27017"
    mongo_db: str = "darkwolf"

    tor_host: str = "127.0.0.1"
    tor_socks_port: int = 9050

    inc_ransom_url: str
    inc_ransom_api_base_url: str

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()