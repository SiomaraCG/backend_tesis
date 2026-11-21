"""Configuración de conexión SQLAlchemy con soporte PostgreSQL + PostGIS, MySQL 8 Spatial y fallback local."""
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

BASE_DIR = Path(__file__).resolve().parent.parent.parent
FALLBACK_SQLITE_URL = f"sqlite:///{(BASE_DIR / 'transporte_escolar.db').as_posix()}"

ACTIVE_DB_DIALECT: str = "sqlite"


def _resolve_database_url() -> str:
    """
    Intenta conectarse a PostgreSQL + PostGIS (definido en docker-compose.yml y .env)
    y habilita automáticamente la extensión `postgis`. Si el contenedor Docker aún
    no está encendido, utiliza la base local SQLite como respaldo para desarrollo.
    """
    global ACTIVE_DB_DIALECT
    db_url = settings.DATABASE_URL

    if db_url.startswith("postgresql"):
        try:
            test_engine = create_engine(
                db_url,
                connect_args={"connect_timeout": 3},
                pool_pre_ping=True,
            )
            with test_engine.begin() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            test_engine.dispose()
            ACTIVE_DB_DIALECT = "postgresql"
            return db_url
        except Exception as exc:
            print(
                f"[DB INFO] Contenedor PostgreSQL/PostGIS no disponible ({exc}). "
                f"Usando respaldo local SQLite: {FALLBACK_SQLITE_URL}"
            )
            ACTIVE_DB_DIALECT = "sqlite"
            return FALLBACK_SQLITE_URL

    if db_url.startswith("mysql"):
        try:
            test_engine = create_engine(db_url, pool_pre_ping=True)
            with test_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            test_engine.dispose()
            ACTIVE_DB_DIALECT = "mysql"
            return db_url
        except Exception as exc:
            print(
                f"[DB INFO] MySQL no disponible ({exc}). "
                f"Usando respaldo local SQLite: {FALLBACK_SQLITE_URL}"
            )
            ACTIVE_DB_DIALECT = "sqlite"
            return FALLBACK_SQLITE_URL

    ACTIVE_DB_DIALECT = "sqlite"
    return db_url


ACTIVE_DATABASE_URL = _resolve_database_url()

connect_args = {"check_same_thread": False} if ACTIVE_DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    ACTIVE_DATABASE_URL,
    pool_pre_ping=True,
    connect_args=connect_args,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependencia para inyectar sesión de base de datos por petición."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
