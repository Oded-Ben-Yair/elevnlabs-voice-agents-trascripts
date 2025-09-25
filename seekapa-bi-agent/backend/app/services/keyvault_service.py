"""
Azure Key Vault Service for Secure Secrets Management
Implements best practices for secret rotation and caching
"""
import os
import json
import logging
import asyncio
from typing import Dict, Optional, Any, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from azure.keyvault.secrets.aio import SecretClient
from azure.identity.aio import DefaultAzureCredential, ClientSecretCredential
from azure.core.exceptions import ResourceNotFoundError, AzureError
import aiofiles
from cryptography.fernet import Fernet
import base64

from app.core.security import audit_logger, EncryptionManager

logger = logging.getLogger(__name__)

@dataclass
class SecretMetadata:
    """Metadata for cached secrets"""
    value: str
    version: str
    expires_at: datetime
    last_accessed: datetime
    rotation_required: bool = False

class KeyVaultService:
    """
    Azure Key Vault integration for secure secrets management
    Implements caching, rotation, and encryption at rest
    """

    def __init__(self,
                vault_url: Optional[str] = None,
                tenant_id: Optional[str] = None,
                client_id: Optional[str] = None,
                client_secret: Optional[str] = None,
                cache_ttl: int = 3600):
        """
        Initialize Key Vault service

        Args:
            vault_url: Azure Key Vault URL
            tenant_id: Azure AD tenant ID
            client_id: Service principal client ID
            client_secret: Service principal secret
            cache_ttl: Cache time-to-live in seconds
        """
        self.vault_url = vault_url or os.getenv("AZURE_KEY_VAULT_URL")
        self.cache_ttl = cache_ttl
        self.secret_cache: Dict[str, SecretMetadata] = {}
        self.encryption_manager = EncryptionManager()

        # Initialize Azure credentials
        if tenant_id and client_id and client_secret:
            self.credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret
            )
        else:
            # Use default credential chain (managed identity, CLI, etc.)
            self.credential = DefaultAzureCredential()

        # Initialize Key Vault client
        if self.vault_url:
            self.client = SecretClient(
                vault_url=self.vault_url,
                credential=self.credential
            )
            self.enabled = True
            logger.info(f"Key Vault service initialized with URL: {self.vault_url}")
        else:
            self.client = None
            self.enabled = False
            logger.warning("Key Vault service disabled - no vault URL provided")

    async def get_secret(self, secret_name: str, use_cache: bool = True) -> Optional[str]:
        """
        Retrieve a secret from Key Vault with caching

        Args:
            secret_name: Name of the secret
            use_cache: Whether to use cached value if available

        Returns:
            Secret value or None if not found
        """
        if not self.enabled:
            # Fall back to environment variables
            return os.getenv(secret_name.upper().replace("-", "_"))

        try:
            # Check cache first
            if use_cache and secret_name in self.secret_cache:
                cached = self.secret_cache[secret_name]
                if datetime.utcnow() < cached.expires_at:
                    cached.last_accessed = datetime.utcnow()
                    logger.debug(f"Retrieved secret '{secret_name}' from cache")
                    return cached.value

            # Fetch from Key Vault
            async with self.client:
                secret = await self.client.get_secret(secret_name)

                # Cache the secret
                self.secret_cache[secret_name] = SecretMetadata(
                    value=secret.value,
                    version=secret.properties.version,
                    expires_at=datetime.utcnow() + timedelta(seconds=self.cache_ttl),
                    last_accessed=datetime.utcnow()
                )

                logger.info(f"Retrieved secret '{secret_name}' from Key Vault")

                # Log audit event
                audit_logger.log_security_event(
                    event_type="KEY_VAULT_SECRET_ACCESSED",
                    severity="LOW",
                    user_id="system",
                    ip_address="internal",
                    details={
                        "secret_name": secret_name,
                        "version": secret.properties.version
                    }
                )

                return secret.value

        except ResourceNotFoundError:
            logger.error(f"Secret '{secret_name}' not found in Key Vault")
            # Fall back to environment variable
            return os.getenv(secret_name.upper().replace("-", "_"))

        except AzureError as e:
            logger.error(f"Azure Key Vault error: {str(e)}")
            audit_logger.log_security_event(
                event_type="KEY_VAULT_ERROR",
                severity="HIGH",
                user_id="system",
                ip_address="internal",
                details={
                    "error": str(e),
                    "secret_name": secret_name
                }
            )
            # Fall back to environment variable
            return os.getenv(secret_name.upper().replace("-", "_"))

    async def set_secret(self, secret_name: str, secret_value: str) -> bool:
        """
        Store a secret in Key Vault

        Args:
            secret_name: Name of the secret
            secret_value: Value to store

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            logger.warning("Key Vault service disabled - cannot set secret")
            return False

        try:
            async with self.client:
                secret = await self.client.set_secret(secret_name, secret_value)

                # Update cache
                self.secret_cache[secret_name] = SecretMetadata(
                    value=secret_value,
                    version=secret.properties.version,
                    expires_at=datetime.utcnow() + timedelta(seconds=self.cache_ttl),
                    last_accessed=datetime.utcnow()
                )

                logger.info(f"Set secret '{secret_name}' in Key Vault")

                # Log audit event
                audit_logger.log_security_event(
                    event_type="KEY_VAULT_SECRET_UPDATED",
                    severity="MEDIUM",
                    user_id="system",
                    ip_address="internal",
                    details={
                        "secret_name": secret_name,
                        "version": secret.properties.version
                    }
                )

                return True

        except AzureError as e:
            logger.error(f"Failed to set secret: {str(e)}")
            return False

    async def rotate_secret(self, secret_name: str, new_value: str) -> bool:
        """
        Rotate a secret by creating a new version

        Args:
            secret_name: Name of the secret to rotate
            new_value: New secret value

        Returns:
            True if successful, False otherwise
        """
        try:
            # Set new secret version
            success = await self.set_secret(secret_name, new_value)

            if success:
                # Mark for rotation in cache
                if secret_name in self.secret_cache:
                    self.secret_cache[secret_name].rotation_required = False

                # Log rotation event
                audit_logger.log_security_event(
                    event_type="SECRET_ROTATED",
                    severity="HIGH",
                    user_id="system",
                    ip_address="internal",
                    details={
                        "secret_name": secret_name,
                        "action": "rotation_completed"
                    }
                )

                return True

        except Exception as e:
            logger.error(f"Secret rotation failed: {str(e)}")

        return False

    async def list_secrets(self) -> List[Dict[str, Any]]:
        """
        List all secrets in the Key Vault

        Returns:
            List of secret properties
        """
        if not self.enabled:
            return []

        secrets = []
        try:
            async with self.client:
                async for secret_properties in self.client.list_properties_of_secrets():
                    secrets.append({
                        "name": secret_properties.name,
                        "enabled": secret_properties.enabled,
                        "created": secret_properties.created_on.isoformat() if secret_properties.created_on else None,
                        "updated": secret_properties.updated_on.isoformat() if secret_properties.updated_on else None,
                        "expires": secret_properties.expires_on.isoformat() if secret_properties.expires_on else None
                    })

        except AzureError as e:
            logger.error(f"Failed to list secrets: {str(e)}")

        return secrets

    async def delete_secret(self, secret_name: str) -> bool:
        """
        Delete a secret from Key Vault (soft delete)

        Args:
            secret_name: Name of the secret to delete

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled:
            return False

        try:
            async with self.client:
                await self.client.begin_delete_secret(secret_name)

                # Remove from cache
                if secret_name in self.secret_cache:
                    del self.secret_cache[secret_name]

                logger.info(f"Deleted secret '{secret_name}' from Key Vault")

                # Log deletion event
                audit_logger.log_security_event(
                    event_type="SECRET_DELETED",
                    severity="HIGH",
                    user_id="system",
                    ip_address="internal",
                    details={
                        "secret_name": secret_name
                    }
                )

                return True

        except AzureError as e:
            logger.error(f"Failed to delete secret: {str(e)}")
            return False

    async def backup_secret(self, secret_name: str, backup_path: str) -> bool:
        """
        Backup a secret to encrypted local storage

        Args:
            secret_name: Name of the secret to backup
            backup_path: Path to store the backup

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get the secret
            secret_value = await self.get_secret(secret_name, use_cache=False)
            if not secret_value:
                return False

            # Encrypt the secret
            encrypted_value = self.encryption_manager.encrypt_data(secret_value)

            # Create backup data
            backup_data = {
                "secret_name": secret_name,
                "encrypted_value": encrypted_value,
                "backup_time": datetime.utcnow().isoformat(),
                "vault_url": self.vault_url
            }

            # Write to file
            async with aiofiles.open(backup_path, 'w') as f:
                await f.write(json.dumps(backup_data, indent=2))

            logger.info(f"Backed up secret '{secret_name}' to {backup_path}")

            return True

        except Exception as e:
            logger.error(f"Failed to backup secret: {str(e)}")
            return False

    async def restore_secret(self, backup_path: str) -> bool:
        """
        Restore a secret from encrypted backup

        Args:
            backup_path: Path to the backup file

        Returns:
            True if successful, False otherwise
        """
        try:
            # Read backup file
            async with aiofiles.open(backup_path, 'r') as f:
                backup_data = json.loads(await f.read())

            # Decrypt the value
            secret_value = self.encryption_manager.decrypt_data(backup_data['encrypted_value'])

            # Restore to Key Vault
            success = await self.set_secret(backup_data['secret_name'], secret_value)

            if success:
                logger.info(f"Restored secret '{backup_data['secret_name']}' from backup")

            return success

        except Exception as e:
            logger.error(f"Failed to restore secret: {str(e)}")
            return False

    def clear_cache(self):
        """Clear the secret cache"""
        self.secret_cache.clear()
        logger.info("Secret cache cleared")

    async def close(self):
        """Close Key Vault connections"""
        if self.client:
            await self.client.close()
        if self.credential:
            await self.credential.close()

class EnvFileManager:
    """
    Manage .env file migration to Key Vault
    """

    def __init__(self, keyvault_service: KeyVaultService):
        self.keyvault = keyvault_service

    async def migrate_env_to_keyvault(self, env_file_path: str = "../.env") -> Dict[str, bool]:
        """
        Migrate environment variables from .env file to Key Vault

        Args:
            env_file_path: Path to .env file

        Returns:
            Dictionary of migration results
        """
        results = {}

        try:
            # Read .env file
            async with aiofiles.open(env_file_path, 'r') as f:
                lines = await f.readlines()

            for line in lines:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")

                    # Convert to Key Vault naming convention
                    secret_name = key.lower().replace('_', '-')

                    # Store in Key Vault
                    success = await self.keyvault.set_secret(secret_name, value)
                    results[key] = success

                    if success:
                        logger.info(f"Migrated {key} to Key Vault as {secret_name}")
                    else:
                        logger.error(f"Failed to migrate {key}")

            # Log migration event
            audit_logger.log_security_event(
                event_type="ENV_MIGRATION_TO_KEYVAULT",
                severity="HIGH",
                user_id="system",
                ip_address="internal",
                details={
                    "total_vars": len(results),
                    "successful": sum(1 for v in results.values() if v),
                    "failed": sum(1 for v in results.values() if not v)
                }
            )

        except Exception as e:
            logger.error(f"Failed to migrate .env file: {str(e)}")

        return results

    async def generate_env_template(self, output_path: str = "../.env.template") -> bool:
        """
        Generate .env template file with Key Vault references

        Args:
            output_path: Path for template file

        Returns:
            True if successful, False otherwise
        """
        try:
            # Get list of secrets
            secrets = await self.keyvault.list_secrets()

            template_lines = [
                "# Environment Variables Template",
                "# These values are stored in Azure Key Vault",
                f"# Vault URL: {self.keyvault.vault_url}",
                "",
                "# To use Key Vault secrets, set these environment variables:",
                "AZURE_KEY_VAULT_URL=<your-vault-url>",
                "AZURE_TENANT_ID=<your-tenant-id>",
                "AZURE_CLIENT_ID=<your-client-id>",
                "AZURE_CLIENT_SECRET=<your-client-secret>",
                "",
                "# Available secrets in Key Vault:",
            ]

            for secret in secrets:
                env_var = secret['name'].upper().replace('-', '_')
                template_lines.append(f"# {env_var}=<stored-in-keyvault>")

            # Write template file
            async with aiofiles.open(output_path, 'w') as f:
                await f.write('\n'.join(template_lines))

            logger.info(f"Generated .env template at {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to generate .env template: {str(e)}")
            return False

# Singleton instance
_keyvault_service: Optional[KeyVaultService] = None

def get_keyvault_service() -> KeyVaultService:
    """Get or create Key Vault service instance"""
    global _keyvault_service
    if _keyvault_service is None:
        _keyvault_service = KeyVaultService()
    return _keyvault_service

# Export main classes
__all__ = [
    'KeyVaultService',
    'EnvFileManager',
    'get_keyvault_service'
]