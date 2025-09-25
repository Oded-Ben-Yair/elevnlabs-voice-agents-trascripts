"""
Tests for database configuration.
"""
import pytest
import os
from unittest.mock import patch

from app.core.database import DatabaseSettings


class TestDatabaseSettings:
    """Test DatabaseSettings functionality."""

    @pytest.mark.unit
    def test_default_configuration(self):
        """Test default database configuration values."""
        config = DatabaseSettings()

        assert config.POSTGRES_HOST == 'localhost'
        assert config.POSTGRES_PORT == 5432
        assert config.POSTGRES_USER == 'seekapa_admin'
        assert config.POSTGRES_PASSWORD == ''
        assert config.POSTGRES_DB == 'seekapa_bi'
        assert config.READ_REPLICA_HOST is None
        assert config.READ_REPLICA_PORT == 5432
        assert config.DB_POOL_SIZE == 10
        assert config.DB_MAX_OVERFLOW == 20
        assert config.DB_POOL_TIMEOUT == 30
        assert config.DB_POOL_RECYCLE == 1800

    @pytest.mark.unit
    def test_environment_variable_override(self):
        """Test configuration override with environment variables."""
        env_vars = {
            'POSTGRES_HOST': 'prod-db.example.com',
            'POSTGRES_PORT': '5433',
            'POSTGRES_USER': 'prod_user',
            'POSTGRES_PASSWORD': 'secure_password',
            'POSTGRES_DB': 'prod_seekapa_bi',
            'READ_REPLICA_HOST': 'replica.example.com',
            'READ_REPLICA_PORT': '5434',
            'DB_POOL_SIZE': '20',
            'DB_MAX_OVERFLOW': '40',
            'DB_POOL_TIMEOUT': '60',
            'DB_POOL_RECYCLE': '3600'
        }

        with patch.dict(os.environ, env_vars):
            config = DatabaseSettings()

        assert config.POSTGRES_HOST == 'prod-db.example.com'
        assert config.POSTGRES_PORT == 5433
        assert config.POSTGRES_USER == 'prod_user'
        assert config.POSTGRES_PASSWORD == 'secure_password'
        assert config.POSTGRES_DB == 'prod_seekapa_bi'
        assert config.READ_REPLICA_HOST == 'replica.example.com'
        assert config.READ_REPLICA_PORT == 5434
        assert config.DB_POOL_SIZE == 20
        assert config.DB_MAX_OVERFLOW == 40
        assert config.DB_POOL_TIMEOUT == 60
        assert config.DB_POOL_RECYCLE == 3600

    @pytest.mark.unit
    def test_sqlalchemy_database_uri_generation(self):
        """Test PostgreSQL connection string generation."""
        config = DatabaseSettings()
        config.POSTGRES_HOST = 'testhost'
        config.POSTGRES_PORT = 5432
        config.POSTGRES_USER = 'testuser'
        config.POSTGRES_PASSWORD = 'testpass'
        config.POSTGRES_DB = 'testdb'

        expected_uri = 'postgresql://testuser:testpass@testhost:5432/testdb'
        assert config.SQLALCHEMY_DATABASE_URI == expected_uri

    @pytest.mark.unit
    def test_sqlalchemy_database_uri_without_password(self):
        """Test PostgreSQL connection string generation without password."""
        config = DatabaseSettings()
        config.POSTGRES_HOST = 'testhost'
        config.POSTGRES_PORT = 5432
        config.POSTGRES_USER = 'testuser'
        config.POSTGRES_PASSWORD = ''
        config.POSTGRES_DB = 'testdb'

        expected_uri = 'postgresql://testuser:@testhost:5432/testdb'
        assert config.SQLALCHEMY_DATABASE_URI == expected_uri

    @pytest.mark.unit
    def test_read_replica_uri_when_configured(self):
        """Test read replica URI generation when replica is configured."""
        config = DatabaseSettings()
        config.POSTGRES_USER = 'testuser'
        config.POSTGRES_PASSWORD = 'testpass'
        config.POSTGRES_DB = 'testdb'
        config.READ_REPLICA_HOST = 'replica.testhost.com'
        config.READ_REPLICA_PORT = 5433

        expected_uri = 'postgresql://testuser:testpass@replica.testhost.com:5433/testdb'
        assert config.READ_REPLICA_URI == expected_uri

    @pytest.mark.unit
    def test_read_replica_uri_when_not_configured(self):
        """Test read replica URI when no replica is configured."""
        config = DatabaseSettings()
        config.READ_REPLICA_HOST = None

        assert config.READ_REPLICA_URI is None

    @pytest.mark.unit
    def test_connection_options(self):
        """Test database connection options generation."""
        config = DatabaseSettings()
        config.DB_POOL_SIZE = 15
        config.DB_MAX_OVERFLOW = 30
        config.DB_POOL_TIMEOUT = 45
        config.DB_POOL_RECYCLE = 7200

        options = config.get_connection_options()

        expected_options = {
            'pool_size': 15,
            'max_overflow': 30,
            'pool_timeout': 45,
            'pool_recycle': 7200,
            'pool_pre_ping': True
        }

        assert options == expected_options

    @pytest.mark.unit
    def test_connection_options_defaults(self):
        """Test default connection options."""
        config = DatabaseSettings()

        options = config.get_connection_options()

        assert options['pool_size'] == 10
        assert options['max_overflow'] == 20
        assert options['pool_timeout'] == 30
        assert options['pool_recycle'] == 1800
        assert options['pool_pre_ping'] is True

    @pytest.mark.unit
    def test_special_characters_in_password(self):
        """Test handling of special characters in password."""
        config = DatabaseSettings()
        config.POSTGRES_HOST = 'localhost'
        config.POSTGRES_PORT = 5432
        config.POSTGRES_USER = 'user'
        config.POSTGRES_PASSWORD = 'p@ssw0rd!#$%'
        config.POSTGRES_DB = 'testdb'

        expected_uri = 'postgresql://user:p@ssw0rd!#$%@localhost:5432/testdb'
        assert config.SQLALCHEMY_DATABASE_URI == expected_uri

    @pytest.mark.unit
    def test_numeric_port_handling(self):
        """Test that ports are properly handled as integers."""
        env_vars = {
            'POSTGRES_PORT': '5433',
            'READ_REPLICA_PORT': '5434'
        }

        with patch.dict(os.environ, env_vars):
            config = DatabaseSettings()

        assert isinstance(config.POSTGRES_PORT, int)
        assert isinstance(config.READ_REPLICA_PORT, int)
        assert config.POSTGRES_PORT == 5433
        assert config.READ_REPLICA_PORT == 5434

    @pytest.mark.unit
    def test_pool_configuration_validation(self):
        """Test pool configuration with various values."""
        config = DatabaseSettings()

        # Test minimum values
        config.DB_POOL_SIZE = 1
        config.DB_MAX_OVERFLOW = 0
        config.DB_POOL_TIMEOUT = 1
        config.DB_POOL_RECYCLE = 60

        options = config.get_connection_options()

        assert options['pool_size'] == 1
        assert options['max_overflow'] == 0
        assert options['pool_timeout'] == 1
        assert options['pool_recycle'] == 60

    @pytest.mark.unit
    def test_development_configuration(self):
        """Test typical development environment configuration."""
        env_vars = {
            'POSTGRES_HOST': 'localhost',
            'POSTGRES_PORT': '5432',
            'POSTGRES_USER': 'dev_user',
            'POSTGRES_PASSWORD': 'dev_password',
            'POSTGRES_DB': 'seekapa_bi_dev',
            'DB_POOL_SIZE': '5',
            'DB_MAX_OVERFLOW': '10'
        }

        with patch.dict(os.environ, env_vars):
            config = DatabaseSettings()

        assert config.POSTGRES_HOST == 'localhost'
        assert config.POSTGRES_USER == 'dev_user'
        assert config.POSTGRES_DB == 'seekapa_bi_dev'
        assert config.DB_POOL_SIZE == 5
        assert config.DB_MAX_OVERFLOW == 10
        assert config.READ_REPLICA_HOST is None

        uri = config.SQLALCHEMY_DATABASE_URI
        assert 'dev_user:dev_password' in uri
        assert 'seekapa_bi_dev' in uri

    @pytest.mark.unit
    def test_production_configuration(self):
        """Test typical production environment configuration."""
        env_vars = {
            'POSTGRES_HOST': 'prod-db.company.com',
            'POSTGRES_PORT': '5432',
            'POSTGRES_USER': 'prod_user',
            'POSTGRES_PASSWORD': 'very_secure_password_123',
            'POSTGRES_DB': 'seekapa_bi_prod',
            'READ_REPLICA_HOST': 'prod-replica.company.com',
            'READ_REPLICA_PORT': '5432',
            'DB_POOL_SIZE': '20',
            'DB_MAX_OVERFLOW': '40',
            'DB_POOL_TIMEOUT': '60',
            'DB_POOL_RECYCLE': '3600'
        }

        with patch.dict(os.environ, env_vars):
            config = DatabaseSettings()

        # Test primary database configuration
        assert config.POSTGRES_HOST == 'prod-db.company.com'
        assert config.POSTGRES_USER == 'prod_user'
        assert config.POSTGRES_DB == 'seekapa_bi_prod'
        assert config.DB_POOL_SIZE == 20
        assert config.DB_MAX_OVERFLOW == 40

        # Test read replica configuration
        assert config.READ_REPLICA_HOST == 'prod-replica.company.com'
        assert config.READ_REPLICA_URI is not None

        primary_uri = config.SQLALCHEMY_DATABASE_URI
        replica_uri = config.READ_REPLICA_URI

        assert 'prod-db.company.com' in primary_uri
        assert 'prod-replica.company.com' in replica_uri
        assert 'seekapa_bi_prod' in primary_uri
        assert 'seekapa_bi_prod' in replica_uri

    @pytest.mark.unit
    def test_test_environment_configuration(self):
        """Test typical test environment configuration."""
        env_vars = {
            'POSTGRES_HOST': 'localhost',
            'POSTGRES_PORT': '5433',  # Different port for test
            'POSTGRES_USER': 'test_user',
            'POSTGRES_PASSWORD': 'test_password',
            'POSTGRES_DB': 'seekapa_bi_test',
            'DB_POOL_SIZE': '1',      # Minimal pool for tests
            'DB_MAX_OVERFLOW': '0',
            'DB_POOL_TIMEOUT': '5',
            'DB_POOL_RECYCLE': '300'
        }

        with patch.dict(os.environ, env_vars):
            config = DatabaseSettings()

        assert config.POSTGRES_PORT == 5433
        assert config.POSTGRES_DB == 'seekapa_bi_test'
        assert config.DB_POOL_SIZE == 1
        assert config.DB_MAX_OVERFLOW == 0

        options = config.get_connection_options()
        assert options['pool_size'] == 1
        assert options['max_overflow'] == 0
        assert options['pool_timeout'] == 5

    @pytest.mark.unit
    def test_model_config_attributes(self):
        """Test that model config is properly set."""
        config = DatabaseSettings()

        assert hasattr(config, 'model_config')
        assert config.model_config.env_file == '.env'
        assert config.model_config.env_file_encoding == 'utf-8'
        assert config.model_config.extra == 'ignore'

    @pytest.mark.unit
    def test_empty_string_values(self):
        """Test handling of empty string values from environment."""
        env_vars = {
            'POSTGRES_HOST': '',
            'POSTGRES_USER': '',
            'POSTGRES_PASSWORD': '',
            'POSTGRES_DB': ''
        }

        with patch.dict(os.environ, env_vars):
            config = DatabaseSettings()

        # These should be set to empty strings from environment
        assert config.POSTGRES_HOST == ''
        assert config.POSTGRES_USER == ''
        assert config.POSTGRES_PASSWORD == ''
        assert config.POSTGRES_DB == ''

    @pytest.mark.unit
    def test_connection_string_with_empty_values(self):
        """Test connection string generation with empty values."""
        config = DatabaseSettings()
        config.POSTGRES_HOST = ''
        config.POSTGRES_PORT = 5432
        config.POSTGRES_USER = ''
        config.POSTGRES_PASSWORD = ''
        config.POSTGRES_DB = ''

        expected_uri = 'postgresql://:@:5432/'
        assert config.SQLALCHEMY_DATABASE_URI == expected_uri

    @pytest.mark.integration
    @pytest.mark.database
    def test_database_settings_singleton(self):
        """Test that database_config works as expected singleton."""
        from app.core.database import database_config

        # This should be the global instance
        assert isinstance(database_config, DatabaseSettings)
        assert database_config.POSTGRES_HOST is not None
        assert database_config.POSTGRES_PORT is not None

    @pytest.mark.unit
    def test_invalid_port_environment_variables(self):
        """Test handling of invalid port values in environment variables."""
        env_vars = {
            'POSTGRES_PORT': 'invalid_port',
            'READ_REPLICA_PORT': 'also_invalid'
        }

        with patch.dict(os.environ, env_vars):
            # This should not raise an exception but might use defaults
            # The exact behavior depends on pydantic's validation
            try:
                config = DatabaseSettings()
                # If it doesn't raise, check that we got some reasonable values
                assert isinstance(config.POSTGRES_PORT, int)
                assert isinstance(config.READ_REPLICA_PORT, int)
            except ValueError:
                # It's also acceptable for pydantic to raise a validation error
                pass

    @pytest.mark.unit
    def test_large_pool_configuration(self):
        """Test configuration with large pool values."""
        config = DatabaseSettings()
        config.DB_POOL_SIZE = 100
        config.DB_MAX_OVERFLOW = 200
        config.DB_POOL_TIMEOUT = 300
        config.DB_POOL_RECYCLE = 86400  # 24 hours

        options = config.get_connection_options()

        assert options['pool_size'] == 100
        assert options['max_overflow'] == 200
        assert options['pool_timeout'] == 300
        assert options['pool_recycle'] == 86400
        assert options['pool_pre_ping'] is True

    @pytest.mark.unit
    def test_computed_field_properties(self):
        """Test that computed fields work as properties."""
        config = DatabaseSettings()
        config.POSTGRES_HOST = 'example.com'
        config.POSTGRES_PORT = 5432
        config.POSTGRES_USER = 'testuser'
        config.POSTGRES_PASSWORD = 'testpass'
        config.POSTGRES_DB = 'testdb'

        # These should be accessible as properties
        primary_uri = config.SQLALCHEMY_DATABASE_URI
        replica_uri = config.READ_REPLICA_URI

        assert isinstance(primary_uri, str)
        assert primary_uri.startswith('postgresql://')
        assert replica_uri is None  # No replica configured

        # Set replica and test again
        config.READ_REPLICA_HOST = 'replica.example.com'
        replica_uri = config.READ_REPLICA_URI

        assert isinstance(replica_uri, str)
        assert replica_uri.startswith('postgresql://')
        assert 'replica.example.com' in replica_uri