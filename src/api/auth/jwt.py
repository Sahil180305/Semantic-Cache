"""Authentication middleware and utilities."""

from fastapi import FastAPI, Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging

from ..config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer()


class TokenPayload:
    """JWT token payload."""
    
    def __init__(self, sub: str, tenant_id: str, role: str, scopes: list):
        self.sub = sub
        self.tenant_id = tenant_id
        self.role = role
        self.scopes = scopes


def create_access_token(
    subject: str,
    tenant_id: str,
    role: str = "user",
    scopes: Optional[list] = None,
    expires_delta: Optional[timedelta] = None
) -> str:
    """Create JWT access token."""
    if expires_delta is None:
        expires_delta = timedelta(hours=settings.JWT_EXPIRATION_HOURS)
    
    if scopes is None:
        scopes = ["cache:read", "cache:write"]
    
    expire = datetime.utcnow() + expires_delta
    
    to_encode = {
        "sub": subject,
        "tenant_id": tenant_id,
        "role": role,
        "scopes": scopes,
        "exp": expire
    }
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    
    return encoded_jwt


async def verify_token(
    credentials: HTTPAuthorizationCredentials,
) -> TokenPayload:
    """Verify JWT token."""
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        
        sub: str = payload.get("sub")
        tenant_id: str = payload.get("tenant_id")
        role: str = payload.get("role", "user")
        scopes: list = payload.get("scopes", [])
        
        if sub is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        return TokenPayload(
            sub=sub,
            tenant_id=tenant_id,
            role=role,
            scopes=scopes
        )
    
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> TokenPayload:
    """Get current authenticated user."""
    return await verify_token(credentials)


async def get_current_admin(
    current_user: TokenPayload = Depends(get_current_user),
) -> TokenPayload:
    """Get current user and verify admin role."""
    if current_user.role not in ["admin", "superadmin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


async def get_current_superadmin(
    current_user: TokenPayload = Depends(get_current_user),
) -> TokenPayload:
    """Get current user and verify superadmin role."""
    if current_user.role != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin access required"
        )
    return current_user


async def check_scope(
    required_scope: str,
    current_user: TokenPayload = Depends(get_current_user),
) -> TokenPayload:
    """Check if user has required scope."""
    if required_scope not in current_user.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Scope {required_scope} required"
        )
    return current_user


async def get_tenant_id(
    x_tenant_id: Optional[str] = Header(None),
    current_user: TokenPayload = Depends(get_current_user),
) -> str:
    """Get tenant ID from header or user token."""
    # Use header if provided and user is admin
    if x_tenant_id and current_user.role in ["admin", "superadmin"]:
        return x_tenant_id
    
    # Otherwise use user's tenant
    return current_user.tenant_id


def add_auth_middleware(app: FastAPI):
    """Add authentication middleware to FastAPI app."""
    
    @app.get("/token")
    async def generate_token(
        user_id: str,
        tenant_id: str,
        role: str = "user"
    ) -> Dict[str, str]:
        """Generate access token for testing."""
        if settings.ENVIRONMENT != "development":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Token generation only available in development"
            )
        
        token = create_access_token(
            subject=user_id,
            tenant_id=tenant_id,
            role=role
        )
        
        return {"access_token": token, "token_type": "bearer"}
