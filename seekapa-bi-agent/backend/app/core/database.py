from typing import Optional
import os
from pydantic import PostgresDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

class DatabaseSettings(BaseSettings):
    """Database configuration settings"""
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore'
    )

    # PostgreSQL Connection
    POSTGRES_HOST: str = 'localhost'
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = 'seekapa_admin'
    POSTGRES_PASSWORD: str = ''
    POSTGRES_DB: str = 'seekapa_bi'

    # Read Replica Configuration
    READ_REPLICA_HOST: Optional[str] = None
    READ_REPLICA_PORT: int = 5432

    # Connection Pool Settings
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    @computed_field
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        """Generate full PostgreSQL connection string"""
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @computed_field
    @property
    def READ_REPLICA_URI(self) -> Optional[PostgresDsn]:
        """Generate read replica connection string if configured"""
        if self.READ_REPLICA_HOST:
            return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.READ_REPLICA_HOST}:{self.READ_REPLICA_PORT}/{self.POSTGRES_DB}"
        return None

    def get_connection_options(self) -> dict:
        """Provide database connection pool configuration"""
        return {
            'pool_size': self.DB_POOL_SIZE,
            'max_overflow': self.DB_MAX_OVERFLOW,
            'pool_timeout': self.DB_POOL_TIMEOUT,
            'pool_recycle': self.DB_POOL_RECYCLE,
            'pool_pre_ping': True  # Test connection health before use
        }

# Singleton database configuration instance
database_config = DatabaseSettings()