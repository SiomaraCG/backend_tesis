"""Configuración central leída desde variables de entorno (.env)."""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    PROJECT_NAME: str = "API Sistema de Gestión y Monitoreo de Transporte Escolar"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api"
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgrespassword@localhost:5435/transporte_escolar"
    SECRET_KEY: str = "clave_secreta_super_segura_cambiar_en_produccion_tesis_2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720
    OSRM_BASE_URL: str = "http://router.project-osrm.org"

    model_config = SettingsConfigDict(env_file=str(BACKEND_ENV_PATH), extra="ignore")


settings = Settings()

