"""
Security Middleware implementing OAuth 2.1 with PKCE and other security measures
"""
import secrets
import hashlib
import base64
import time
import json
import logging
from typing import Optional, Dict, Callable
from fastapi import Request, Response, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import jwt
from datetime import datetime, timedelta

from app.core.security import (
    InputValidator,
    TokenManager,
    audit_logger,
    SecurityLevel,
    RBACManager,
    csrf_protection
)

# Configure logger
logger = logging.getLogger(__name__)

# OAuth2 configuration
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
bearer_scheme = HTTPBearer()

class OAuth2PKCEMiddleware(BaseHTTPMiddleware):
    """
    OAuth 2.1 with PKCE (Proof Key for Code Exchange) implementation
    Follows RFC 7636 and OAuth 2.1 specifications
    """

    def __init__(self, app, secret_key: str = None):
        super().__init__(app)
        self.secret_key = secret_key or secrets.token_urlsafe(32)
        self.token_manager = TokenManager(self.secret_key)
        self.pending_challenges = {}  # Store PKCE challenges
        self.authorization_codes = {}  # Store temporary auth codes

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with OAuth 2.1 PKCE validation"""

        # Skip auth for public endpoints
        if self._is_public_endpoint(request.url.path):
            return await call_next(request)

        # Extract and validate token
        token = await self._extract_token(request)
        if not token:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authentication required"},
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Verify token
        payload = self.token_manager.verify_token(token)
        if not payload:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid or expired token"},
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Check permissions
        user_role = SecurityLevel(payload.get('role', 'read_only'))
        if not self._check_endpoint_permission(request.url.path, request.method, user_role):
            audit_logger.log_security_event(
                event_type="UNAUTHORIZED_ACCESS_ATTEMPT",
                severity="HIGH",
                user_id=payload.get('user_id'),
                ip_address=request.client.host,
                details={
                    "endpoint": request.url.path,
                    "method": request.method,
                    "role": user_role.value
                }
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Insufficient permissions"}
            )

        # Add user context to request
        request.state.user_id = payload.get('user_id')
        request.state.user_role = user_role
        request.state.token_jti = payload.get('jti')

        response = await call_next(request)
        return response

    def generate_pkce_challenge(self) -> Dict[str, str]:
        """Generate PKCE code verifier and challenge"""
        # Generate code verifier (43-128 characters)
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')

        # Generate code challenge using SHA256
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).decode('utf-8').rstrip('=')

        return {
            'code_verifier': code_verifier,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256'
        }

    def create_authorization_code(self,
                                 client_id: str,
                                 redirect_uri: str,
                                 code_challenge: str,
                                 scope: str,
                                 user_id: str) -> str:
        """Create authorization code for OAuth flow"""
        code = secrets.token_urlsafe(32)

        # Store with expiry (10 minutes)
        self.authorization_codes[code] = {
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'code_challenge': code_challenge,
            'scope': scope,
            'user_id': user_id,
            'expires_at': time.time() + 600
        }

        return code

    def exchange_code_for_token(self,
                               code: str,
                               code_verifier: str,
                               client_id: str,
                               redirect_uri: str) -> Optional[Dict[str, str]]:
        """Exchange authorization code for access token with PKCE verification"""

        # Validate authorization code
        auth_data = self.authorization_codes.get(code)
        if not auth_data:
            logger.warning(f"Invalid authorization code attempt: {code[:10]}...")
            return None

        # Check expiry
        if time.time() > auth_data['expires_at']:
            del self.authorization_codes[code]
            logger.warning("Expired authorization code used")
            return None

        # Validate client_id and redirect_uri
        if auth_data['client_id'] != client_id or auth_data['redirect_uri'] != redirect_uri:
            logger.warning("Client ID or redirect URI mismatch")
            return None

        # Verify PKCE challenge
        expected_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).decode('utf-8').rstrip('=')

        if expected_challenge != auth_data['code_challenge']:
            logger.warning("PKCE challenge verification failed")
            audit_logger.log_security_event(
                event_type="PKCE_VERIFICATION_FAILED",
                severity="HIGH",
                user_id=auth_data['user_id'],
                ip_address="unknown",
                details={"client_id": client_id}
            )
            return None

        # Clean up used code
        del self.authorization_codes[code]

        # Generate tokens
        access_token = self.token_manager.generate_token(
            user_id=auth_data['user_id'],
            role=SecurityLevel.READ_ONLY,  # Default role
            expires_in=3600
        )

        refresh_token = self.token_manager.generate_token(
            user_id=auth_data['user_id'],
            role=SecurityLevel.READ_ONLY,
            expires_in=86400  # 24 hours
        )

        return {
            'access_token': access_token,
            'token_type': 'Bearer',
            'expires_in': 3600,
            'refresh_token': refresh_token,
            'scope': auth_data['scope']
        }

    async def _extract_token(self, request: Request) -> Optional[str]:
        """Extract bearer token from request"""
        authorization = request.headers.get("Authorization")
        if not authorization:
            return None

        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None

        return parts[1]

    def _is_public_endpoint(self, path: str) -> bool:
        """Check if endpoint is public"""
        public_endpoints = [
            "/",
            "/health",
            "/docs",
            "/openapi.json",
            "/oauth/authorize",
            "/oauth/token",
            "/api/v1/public"
        ]
        return path in public_endpoints or path.startswith("/static")

    def _check_endpoint_permission(self, path: str, method: str, role: SecurityLevel) -> bool:
        """Check if role has permission for endpoint"""

        # Define endpoint permissions
        endpoint_permissions = {
            "/api/v1/query": {
                "GET": "execute_basic_queries",
                "POST": "execute_basic_queries"
            },
            "/api/v1/powerbi": {
                "GET": "read_private_reports",
                "POST": "write_data"
            },
            "/api/v1/admin": {
                "GET": "admin_access",
                "POST": "admin_access",
                "DELETE": "admin_access"
            }
        }

        # Check if endpoint has defined permissions
        for endpoint_pattern, methods in endpoint_permissions.items():
            if path.startswith(endpoint_pattern):
                required_permission = methods.get(method)
                if required_permission:
                    return RBACManager.check_permission(role, required_permission)

        # Default to allowing read-only access
        if method == "GET":
            return True

        return RBACManager.check_permission(role, "write_data")

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Security headers based on OWASP recommendations
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        # Content Security Policy
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://api.powerbi.com https://*.azure.com; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        response.headers["Content-Security-Policy"] = csp

        # CORS headers (more restrictive than default)
        origin = request.headers.get("origin")
        allowed_origins = [
            "https://app.seekapa.com",
            "https://powerbi.microsoft.com",
            "http://localhost:3000",  # Development
            "http://localhost:5173"   # Vite development
        ]

        if origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-CSRF-Token"
            response.headers["Access-Control-Max-Age"] = "86400"

        return response

class CSRFMiddleware(BaseHTTPMiddleware):
    """CSRF protection for state-changing operations"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip CSRF for GET and OPTIONS
        if request.method in ["GET", "HEAD", "OPTIONS"]:
            return await call_next(request)

        # Skip for API endpoints that use bearer tokens
        if request.url.path.startswith("/api/") and "Authorization" in request.headers:
            return await call_next(request)

        # Check CSRF token for form submissions
        csrf_token = request.headers.get("X-CSRF-Token")
        if not csrf_token:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "CSRF token missing"}
            )

        # Validate CSRF token
        session_id = request.cookies.get("session_id")
        if not session_id or not csrf_protection.validate_token(session_id, csrf_token):
            audit_logger.log_security_event(
                event_type="CSRF_VALIDATION_FAILED",
                severity="HIGH",
                user_id=None,
                ip_address=request.client.host,
                details={"endpoint": request.url.path}
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Invalid CSRF token"}
            )

        return await call_next(request)

class InputValidationMiddleware(BaseHTTPMiddleware):
    """Validate and sanitize all input data"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Validate query parameters
        for param_name, param_value in request.query_params.items():
            if isinstance(param_value, str):
                # Check for injection attempts
                if InputValidator.detect_sql_injection(param_value):
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content={"detail": f"Invalid query parameter: {param_name}"}
                    )

                if InputValidator.detect_xss(param_value):
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content={"detail": f"Invalid query parameter: {param_name}"}
                    )

        # Validate headers
        suspicious_headers = ["X-Forwarded-Host", "X-Original-URL", "X-Rewrite-URL"]
        for header in suspicious_headers:
            if header in request.headers:
                logger.warning(f"Suspicious header detected: {header}")

        # Validate content type for POST/PUT requests
        if request.method in ["POST", "PUT", "PATCH"]:
            content_type = request.headers.get("content-type", "").lower()
            if content_type and not any(ct in content_type for ct in ["application/json", "multipart/form-data", "application/x-www-form-urlencoded"]):
                return JSONResponse(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    content={"detail": "Unsupported media type"}
                )

        # Process request
        response = await call_next(request)
        return response

class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """Log all API calls for audit purposes"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()

        # Extract user information if available
        user_id = getattr(request.state, 'user_id', None)

        # Process request
        response = await call_next(request)

        # Calculate response time
        response_time = time.time() - start_time

        # Log the API call
        audit_logger.log_api_call(
            endpoint=request.url.path,
            method=request.method,
            user_id=user_id,
            ip_address=request.client.host,
            status_code=response.status_code,
            response_time=response_time,
            error=None if response.status_code < 400 else f"HTTP {response.status_code}"
        )

        # Log security events for failed authentication/authorization
        if response.status_code == 401:
            audit_logger.log_security_event(
                event_type="AUTHENTICATION_FAILED",
                severity="MEDIUM",
                user_id=user_id,
                ip_address=request.client.host,
                details={"endpoint": request.url.path}
            )
        elif response.status_code == 403:
            audit_logger.log_security_event(
                event_type="AUTHORIZATION_FAILED",
                severity="MEDIUM",
                user_id=user_id,
                ip_address=request.client.host,
                details={"endpoint": request.url.path}
            )

        return response

# Export middleware instances
__all__ = [
    'OAuth2PKCEMiddleware',
    'SecurityHeadersMiddleware',
    'CSRFMiddleware',
    'InputValidationMiddleware',
    'AuditLoggingMiddleware'
]