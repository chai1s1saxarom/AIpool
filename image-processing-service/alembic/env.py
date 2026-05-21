import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context

# --- Загружаем .env и формируем URL ---
dotenv_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path)

def _sync_database_url() -> str:
    """Alembic требует синхронный драйвер psycopg2."""
    raw = os.getenv("SYNC_DATABASE_URL") or os.getenv("DATABASE_URL")
    if raw:
        return raw.replace("postgresql+asyncpg", "postgresql+psycopg2").replace(
            "asyncpg", "psycopg2"
        )
    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD", "123")
    db_name = os.getenv("DB_NAME", "image_db")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    return f"postgresql+psycopg2://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"


DATABASE_URL = _sync_database_url()
# --- Устанавливаем URL в конфигурацию Alembic ---
config = context.config
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# --- Остальной код (импорт моделей и т.д.) ---
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Импортируем Base после установки URL
from app.database import Base
from app import models  # noqa: F401

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

    pass


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()
    
    pass


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
