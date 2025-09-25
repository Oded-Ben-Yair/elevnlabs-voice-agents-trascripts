"""
OAuth 2.1 Authentication API with PKCE
Implements secure authentication endpoints
"""
import secrets
import hashlib
import base64
from datetime import datetime, timedelta
from typing import Optional, Dict
from fastapi import APIRouter, HTTPException, Request, Response, Depends, Form, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, validator
import re

from app.core.security import (
    TokenManager,
    EncryptionManager,
    InputValidator,
    audit_logger,
    SecurityLevel,
    RBACManager
)
from app.middleware.security import OAuth2PKCEMiddleware

router = APIRouter()

# Initialize services
token_manager = TokenManager()
encryption_manager = EncryptionManager()
oauth_middleware = OAuth2PKCEMiddleware(None)

# Request/Response models
class AuthorizeRequest(BaseModel):
    """OAuth 2.1 Authorization Request"""
    response_type: str
    client_id: str
    redirect_uri: str
    scope: str
    state: str
    code_challenge: str
    code_challenge_method: str = "S256"

    @validator('response_type')
    def validate_response_type(cls, v):
        if v != 'code':
            raise ValueError('Only authorization code flow is supported')
        return v

    @validator('code_challenge_method')
    def validate_challenge_method(cls, v):
        if v != 'S256':
            raise ValueError('Only S256 code challenge method is supported')
        return v

class TokenRequest(BaseModel):
    """OAuth 2.1 Token Request"""
    grant_type: str
    code: Optional[str] = None
    redirect_uri: Optional[str] = None
    client_id: str
    code_verifier: Optional[str] = None
    refresh_token: Optional[str] = None

    @validator('grant_type')
    def validate_grant_type(cls, v):
        if v not in ['authorization_code', 'refresh_token']:
            raise ValueError('Invalid grant type')
        return v

class LoginRequest(BaseModel):
    """User login request"""
    username: str
    password: str

    @validator('username')
    def validate_username(cls, v):
        if not InputValidator.validate_pattern(v, 'email'):
            raise ValueError('Invalid email format')
        return v

class RegisterRequest(BaseModel):
    """User registration request"""
    email: EmailStr
    password: str
    full_name: str
    organization: Optional[str] = None

    @validator('password')
    def validate_password(cls, v):
        """Enforce strong password policy"""
        if len(v) < 12:
            raise ValueError('Password must be at least 12 characters long')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one number')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Password must contain at least one special character')
        return v

class TokenResponse(BaseModel):
    """OAuth 2.1 Token Response"""
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: Optional[str] = None
    scope: str

# Mock user database (in production, use real database)
users_db = {}

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(request: RegisterRequest):
    """
    Register a new user
    Implements secure password hashing and validation
    """
    try:
        # Check if user exists
        if request.email in users_db:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User already exists"
            )

        # Hash password
        password_hash, salt = EncryptionManager.hash_password(request.password)

        # Store user (in production, save to database)
        users_db[request.email] = {
            "email": request.email,
            "password_hash": password_hash,
            "salt": salt,
            "full_name": request.full_name,
            "organization": request.organization,
            "role": SecurityLevel.READ_ONLY.value,
            "created_at": datetime.utcnow().isoformat(),
            "mfa_enabled": False
        }

        # Log registration
        audit_logger.log_security_event(
            event_type="USER_REGISTRATION",
            severity="LOW",
            user_id=request.email,
            ip_address="unknown",
            details={
                "organization": request.organization
            }
        )

        return {
            "message": "User registered successfully",
            "email": request.email
        }

    except HTTPException:
        raise
    except Exception as e:
        audit_logger.log_security_event(
            event_type="REGISTRATION_ERROR",
            severity="HIGH",
            user_id=request.email,
            ip_address="unknown",
            details={"error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )

@router.post("/login")
async def login(request: LoginRequest, response: Response):
    """
    User login endpoint
    Returns session cookie and CSRF token
    """
    try:
        # Validate credentials
        user = users_db.get(request.username)
        if not user:
            # Log failed attempt
            audit_logger.log_security_event(
                event_type="LOGIN_FAILED",
                severity="MEDIUM",
                user_id=request.username,
                ip_address="unknown",
                details={"reason": "user_not_found"}
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        # Verify password
        if not EncryptionManager.verify_password(
            request.password,
            user['password_hash'],
            user['salt']
        ):
            # Log failed attempt
            audit_logger.log_security_event(
                event_type="LOGIN_FAILED",
                severity="MEDIUM",
                user_id=request.username,
                ip_address="unknown",
                details={"reason": "invalid_password"}
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        # Generate session
        session_id = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)

        # Set secure cookie
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=3600
        )

        # Log successful login
        audit_logger.log_security_event(
            event_type="LOGIN_SUCCESS",
            severity="LOW",
            user_id=request.username,
            ip_address="unknown",
            details={}
        )

        return {
            "message": "Login successful",
            "csrf_token": csrf_token,
            "user": {
                "email": user['email'],
                "full_name": user['full_name'],
                "role": user['role']
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )

@router.get("/oauth/authorize")
async def authorize(request: AuthorizeRequest):
    """
    OAuth 2.1 Authorization Endpoint
    Implements PKCE validation
    """
    try:
        # Validate client_id (in production, check against registered clients)
        valid_clients = ["seekapa-web", "seekapa-mobile", "powerbi-connector"]
        if request.client_id not in valid_clients:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid client_id"
            )

        # Validate redirect_uri (must be pre-registered)
        valid_redirects = {
            "seekapa-web": ["https://app.seekapa.com/callback", "http://localhost:3000/callback"],
            "seekapa-mobile": ["seekapa://callback"],
            "powerbi-connector": ["https://app.powerbi.com/redirect"]
        }

        if request.redirect_uri not in valid_redirects.get(request.client_id, []):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid redirect_uri"
            )

        # Validate PKCE code challenge
        if len(request.code_challenge) < 43:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid code_challenge"
            )

        # In production, show login/consent screen
        # For now, auto-approve and generate code
        auth_code = oauth_middleware.create_authorization_code(
            client_id=request.client_id,
            redirect_uri=request.redirect_uri,
            code_challenge=request.code_challenge,
            scope=request.scope,
            user_id="demo_user"  # In production, get from session
        )

        # Log authorization
        audit_logger.log_security_event(
            event_type="OAUTH_AUTHORIZATION",
            severity="LOW",
            user_id="demo_user",
            ip_address="unknown",
            details={
                "client_id": request.client_id,
                "scope": request.scope
            }
        )

        # Return redirect URL
        return {
            "redirect_url": f"{request.redirect_uri}?code={auth_code}&state={request.state}"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authorization failed"
        )

@router.post("/oauth/token", response_model=TokenResponse)
async def token_exchange(request: TokenRequest):
    """
    OAuth 2.1 Token Endpoint
    Exchanges authorization code for access token with PKCE verification
    """
    try:
        if request.grant_type == "authorization_code":
            # Exchange code for token
            if not request.code or not request.code_verifier:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Missing required parameters"
                )

            token_data = oauth_middleware.exchange_code_for_token(
                code=request.code,
                code_verifier=request.code_verifier,
                client_id=request.client_id,
                redirect_uri=request.redirect_uri
            )

            if not token_data:
                audit_logger.log_security_event(
                    event_type="TOKEN_EXCHANGE_FAILED",
                    severity="HIGH",
                    user_id="unknown",
                    ip_address="unknown",
                    details={
                        "client_id": request.client_id,
                        "reason": "invalid_code_or_verifier"
                    }
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid authorization code or verifier"
                )

            return TokenResponse(
                access_token=token_data['access_token'],
                expires_in=token_data['expires_in'],
                refresh_token=token_data.get('refresh_token'),
                scope=token_data['scope']
            )

        elif request.grant_type == "refresh_token":
            # Refresh token flow
            if not request.refresh_token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Missing refresh token"
                )

            # Verify refresh token
            payload = token_manager.verify_token(request.refresh_token)
            if not payload:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid refresh token"
                )

            # Generate new access token
            new_token = token_manager.generate_token(
                user_id=payload['user_id'],
                role=SecurityLevel(payload['role']),
                expires_in=3600
            )

            return TokenResponse(
                access_token=new_token,
                expires_in=3600,
                refresh_token=request.refresh_token,
                scope="read write"
            )

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported grant type"
            )

    except HTTPException:
        raise
    except Exception as e:
        audit_logger.log_security_event(
            event_type="TOKEN_EXCHANGE_ERROR",
            severity="HIGH",
            user_id="unknown",
            ip_address="unknown",
            details={"error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token exchange failed"
        )

@router.post("/logout")
async def logout(request: Request, response: Response):
    """
    Logout endpoint
    Invalidates session and clears cookies
    """
    try:
        # Get session from cookie
        session_id = request.cookies.get("session_id")

        if session_id:
            # Invalidate session (in production, remove from session store)
            # Log logout
            audit_logger.log_security_event(
                event_type="LOGOUT",
                severity="LOW",
                user_id="unknown",
                ip_address="unknown",
                details={}
            )

        # Clear cookies
        response.delete_cookie("session_id")

        return {"message": "Logged out successfully"}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )

@router.get("/oauth/.well-known/openid-configuration")
async def openid_configuration():
    """
    OpenID Connect Discovery Endpoint
    Provides OAuth 2.1 server metadata
    """
    base_url = "https://api.seekapa.com"  # Change in production

    return {
        "issuer": base_url,
        "authorization_endpoint": f"{base_url}/api/v1/auth/oauth/authorize",
        "token_endpoint": f"{base_url}/api/v1/auth/oauth/token",
        "userinfo_endpoint": f"{base_url}/api/v1/auth/userinfo",
        "jwks_uri": f"{base_url}/api/v1/auth/oauth/jwks",
        "scopes_supported": ["openid", "profile", "email", "read", "write"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
        "id_token_signing_alg_values_supported": ["RS256", "HS256"]
    }

# Export router
__all__ = ['router']