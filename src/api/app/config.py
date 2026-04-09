from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    cosmos_endpoint: str
    cosmos_key: str
    cosmos_database: str
    cosmos_container: str
    blob_connection_string: str
    blob_container: str

settings = Settings()  # type: ignore[call-arg]
