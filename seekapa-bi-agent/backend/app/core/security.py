"""
Core Security Module for Seekapa BI Agent
Implements security best practices following OWASP guidelines
"""
import hashlib
import hmac
import secrets
import re
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from functools import wraps
from enum import Enum
import jwt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
import base64

# Configure security logger
security_logger = logging.getLogger("security_audit")
security_logger.setLevel(logging.INFO)

class SecurityLevel(Enum):
    """Security levels for RBAC"""
    PUBLIC = "public"
    READ_ONLY = "read_only"
    ANALYST = "analyst"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"

class InputValidator:
    """Input validation and sanitization following OWASP guidelines"""

    # Regex patterns for common validations
    PATTERNS = {
        'email': r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
        'alphanumeric': r'^[a-zA-Z0-9]+$',
        'safe_string': r'^[a-zA-Z0-9\s\-_.,!?]+$',
        'uuid': r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        'jwt': r'^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+$'
    }

    # SQL injection patterns
    SQL_INJECTION_PATTERNS = [
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|CREATE|ALTER|EXEC|EXECUTE)\b)",
        r"(--|#|\/\*|\*\/)",
        r"(\bOR\b.*=.*)",
        r"(\bAND\b.*=.*)",
        r"(;.*\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|CREATE|ALTER|EXEC|EXECUTE)\b)",
        r"('.*\b(OR|AND)\b.*')",
    ]

    # XSS patterns
    XSS_PATTERNS = [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"on\w+\s*=",
        r"<iframe[^>]*>",
        r"<object[^>]*>",
        r"<embed[^>]*>",
        r"<applet[^>]*>",
        r"<meta[^>]*>",
        r"<link[^>]*>",
        r"<style[^>]*>.*?</style>",
    ]

    # Command injection patterns
    COMMAND_INJECTION_PATTERNS = [
        r"[;&|`$]",
        r"\$\(",
        r"\b(cat|ls|rm|mv|cp|chmod|chown|wget|curl|nc|bash|sh|python|perl)\b",
    ]

    @classmethod
    def validate_pattern(cls, value: str, pattern_name: str) -> bool:
        """Validate input against a predefined pattern"""
        if pattern_name not in cls.PATTERNS:
            return False
        return bool(re.match(cls.PATTERNS[pattern_name], value))

    @classmethod
    def detect_sql_injection(cls, value: str) -> bool:
        """Detect potential SQL injection attempts"""
        value_upper = value.upper()
        for pattern in cls.SQL_INJECTION_PATTERNS:
            if re.search(pattern, value_upper, re.IGNORECASE):
                security_logger.warning(f"SQL injection attempt detected: {value[:50]}...")
                return True
        return False

    @classmethod
    def detect_xss(cls, value: str) -> bool:
        """Detect potential XSS attacks"""
        for pattern in cls.XSS_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                security_logger.warning(f"XSS attempt detected: {value[:50]}...")
                return True
        return False

    @classmethod
    def detect_command_injection(cls, value: str) -> bool:
        """Detect potential command injection attempts"""
        for pattern in cls.COMMAND_INJECTION_PATTERNS:
            if re.search(pattern, value):
                security_logger.warning(f"Command injection attempt detected: {value[:50]}...")
                return True
        return False

    @classmethod
    def sanitize_input(cls, value: str, max_length: int = 1000) -> str:
        """Sanitize input by removing potentially dangerous content"""
        if not value:
            return ""

        # Truncate to max length
        value = value[:max_length]

        # Remove null bytes
        value = value.replace('\0', '')

        # HTML escape
        value = value.replace('<', '&lt;').replace('>', '&gt;')
        value = value.replace('"', '&quot;').replace("'", '&#x27;')
        value = value.replace('&', '&amp;')

        # Remove control characters except newlines and tabs
        value = ''.join(char for char in value if char == '\n' or char == '\t' or ord(char) >= 32)

        return value.strip()

    @classmethod
    def validate_dax_query(cls, query: str) -> Tuple[bool, str]:
        """Validate DAX query for safety"""
        # Check for dangerous patterns
        dangerous_patterns = [
            r"(DROP|DELETE|TRUNCATE|ALTER)\s+TABLE",
            r"(EXEC|EXECUTE)\s*\(",
            r"xp_cmdshell",
            r"sp_executesql",
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                return False, f"Dangerous pattern detected: {pattern}"

        # Ensure query starts with valid DAX keywords
        valid_starts = ['EVALUATE', 'DEFINE', 'VAR', 'MEASURE', 'COLUMN']
        query_upper = query.strip().upper()
        if not any(query_upper.startswith(keyword) for keyword in valid_starts):
            return False, "Invalid DAX query structure"

        return True, "Query validated"

class TokenManager:
    """Secure token management with JWT"""

    def __init__(self, secret_key: str = None):
        self.secret_key = secret_key or secrets.token_urlsafe(32)
        self.algorithm = "HS256"

    def generate_token(self,
                      user_id: str,
                      role: SecurityLevel,
                      expires_in: int = 3600) -> str:
        """Generate a secure JWT token"""
        payload = {
            'user_id': user_id,
            'role': role.value,
            'exp': datetime.utcnow() + timedelta(seconds=expires_in),
            'iat': datetime.utcnow(),
            'jti': secrets.token_urlsafe(16)  # JWT ID for tracking
        }

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        security_logger.info(f"Token generated for user {user_id} with role {role.value}")
        return token

    def verify_token(self, token: str) -> Optional[Dict]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            security_logger.warning("Expired token attempt")
            return None
        except jwt.InvalidTokenError as e:
            security_logger.warning(f"Invalid token: {str(e)}")
            return None

class EncryptionManager:
    """Handle encryption for sensitive data"""

    def __init__(self, master_key: str = None):
        if master_key:
            self.fernet = Fernet(master_key.encode())
        else:
            self.fernet = Fernet(Fernet.generate_key())

    def encrypt_data(self, data: str) -> str:
        """Encrypt sensitive data"""
        return self.fernet.encrypt(data.encode()).decode()

    def decrypt_data(self, encrypted_data: str) -> str:
        """Decrypt sensitive data"""
        return self.fernet.decrypt(encrypted_data.encode()).decode()

    @staticmethod
    def hash_password(password: str, salt: bytes = None) -> Tuple[str, str]:
        """Hash password with PBKDF2"""
        if not salt:
            salt = secrets.token_bytes(32)

        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.b64encode(kdf.derive(password.encode()))
        return key.decode(), base64.b64encode(salt).decode()

    @staticmethod
    def verify_password(password: str, hashed: str, salt: str) -> bool:
        """Verify password against hash"""
        salt_bytes = base64.b64decode(salt.encode())
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt_bytes,
            iterations=100000,
        )
        try:
            kdf.verify(password.encode(), base64.b64decode(hashed.encode()))
            return True
        except:
            return False

class AuditLogger:
    """Comprehensive audit logging"""

    def __init__(self, log_file: str = "security_audit.log"):
        self.logger = logging.getLogger("audit")
        handler = logging.FileHandler(log_file)
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    def log_api_call(self,
                    endpoint: str,
                    method: str,
                    user_id: Optional[str],
                    ip_address: str,
                    status_code: int,
                    response_time: float,
                    error: Optional[str] = None):
        """Log API call details"""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'endpoint': endpoint,
            'method': method,
            'user_id': user_id or 'anonymous',
            'ip_address': ip_address,
            'status_code': status_code,
            'response_time': response_time,
            'error': error
        }

        if status_code >= 400:
            self.logger.error(json.dumps(log_entry))
        else:
            self.logger.info(json.dumps(log_entry))

    def log_security_event(self,
                          event_type: str,
                          severity: str,
                          user_id: Optional[str],
                          ip_address: str,
                          details: Dict):
        """Log security-related events"""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': event_type,
            'severity': severity,
            'user_id': user_id or 'anonymous',
            'ip_address': ip_address,
            'details': details
        }

        if severity in ['HIGH', 'CRITICAL']:
            self.logger.critical(json.dumps(log_entry))
        elif severity == 'MEDIUM':
            self.logger.warning(json.dumps(log_entry))
        else:
            self.logger.info(json.dumps(log_entry))

class RBACManager:
    """Role-Based Access Control implementation"""

    # Permission matrix
    PERMISSIONS = {
        SecurityLevel.PUBLIC: {
            'read_public_reports': True,
            'execute_basic_queries': False,
            'write_data': False,
            'admin_access': False
        },
        SecurityLevel.READ_ONLY: {
            'read_public_reports': True,
            'read_private_reports': True,
            'execute_basic_queries': True,
            'write_data': False,
            'admin_access': False
        },
        SecurityLevel.ANALYST: {
            'read_public_reports': True,
            'read_private_reports': True,
            'execute_basic_queries': True,
            'execute_advanced_queries': True,
            'write_data': True,
            'admin_access': False
        },
        SecurityLevel.ADMIN: {
            'read_public_reports': True,
            'read_private_reports': True,
            'execute_basic_queries': True,
            'execute_advanced_queries': True,
            'write_data': True,
            'manage_users': True,
            'admin_access': True
        },
        SecurityLevel.SUPER_ADMIN: {
            'all_permissions': True
        }
    }

    @classmethod
    def check_permission(cls, role: SecurityLevel, permission: str) -> bool:
        """Check if a role has a specific permission"""
        if role == SecurityLevel.SUPER_ADMIN:
            return True

        role_permissions = cls.PERMISSIONS.get(role, {})
        return role_permissions.get(permission, False)

    @classmethod
    def get_role_permissions(cls, role: SecurityLevel) -> Dict[str, bool]:
        """Get all permissions for a role"""
        return cls.PERMISSIONS.get(role, {})

class SecureSession:
    """Secure session management"""

    def __init__(self):
        self.sessions = {}
        self.session_timeout = 3600  # 1 hour

    def create_session(self, user_id: str, role: SecurityLevel) -> str:
        """Create a new secure session"""
        session_id = secrets.token_urlsafe(32)
        self.sessions[session_id] = {
            'user_id': user_id,
            'role': role,
            'created_at': datetime.utcnow(),
            'last_activity': datetime.utcnow(),
            'ip_address': None,
            'user_agent': None
        }
        return session_id

    def validate_session(self, session_id: str) -> Optional[Dict]:
        """Validate and return session data"""
        session = self.sessions.get(session_id)
        if not session:
            return None

        # Check timeout
        if (datetime.utcnow() - session['last_activity']).total_seconds() > self.session_timeout:
            del self.sessions[session_id]
            return None

        # Update last activity
        session['last_activity'] = datetime.utcnow()
        return session

    def destroy_session(self, session_id: str):
        """Destroy a session"""
        if session_id in self.sessions:
            del self.sessions[session_id]

class CSRFProtection:
    """CSRF token generation and validation"""

    def __init__(self):
        self.tokens = {}

    def generate_token(self, session_id: str) -> str:
        """Generate CSRF token for a session"""
        token = secrets.token_urlsafe(32)
        self.tokens[session_id] = token
        return token

    def validate_token(self, session_id: str, token: str) -> bool:
        """Validate CSRF token"""
        expected_token = self.tokens.get(session_id)
        if not expected_token:
            return False

        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(expected_token, token)

# Initialize global instances
input_validator = InputValidator()
audit_logger = AuditLogger()
rbac_manager = RBACManager()
csrf_protection = CSRFProtection()

# Export main classes and functions
__all__ = [
    'SecurityLevel',
    'InputValidator',
    'TokenManager',
    'EncryptionManager',
    'AuditLogger',
    'RBACManager',
    'SecureSession',
    'CSRFProtection',
    'input_validator',
    'audit_logger',
    'rbac_manager',
    'csrf_protection'
]