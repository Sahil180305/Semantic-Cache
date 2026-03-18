"""Error handling middleware."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class APIException(Exception):
    """Base API exception."""
    
    def __init__(self, code: str, message: str, status_code: int = 400, details=None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class CacheNotFoundException(APIException):
    """Raised when cache key is not found."""
    
    def __init__(self, key: str):
        super().__init__(
            code="CACHE_NOT_FOUND",
            message=f"Key not found in cache: {key}",
            status_code=404,
            details={"key": key}
        )


class QuotaExceededException(APIException):
    """Raised when quota is exceeded."""
    
    def __init__(self, tenant_id: str, quota_type: str):
        super().__init__(
            code="QUOTA_EXCEEDED",
            message=f"Quota exceeded for {quota_type}",
            status_code=429,
            details={"tenant_id": tenant_id, "quota_type": quota_type}
        )


class UnauthorizedException(APIException):
    """Raised when authentication fails."""
    
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(
            code="UNAUTHORIZED",
            message=message,
            status_code=401
        )


class ForbiddenException(APIException):
    """Raised when authorization fails."""
    
    def __init__(self, message: str = "Forbidden"):
        super().__init__(
            code="FORBIDDEN",
            message=message,
            status_code=403
        )


def add_error_handlers(app: FastAPI):
    """Add error handlers to FastAPI app."""
    
    @app.exception_handler(APIException)
    async def api_exception_handler(request: Request, exc: APIException):
        """Handle API exceptions."""
        logger.error(f"API Error: {exc.code} - {exc.message}")
        
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details
                },
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle general exceptions."""
        logger.error(f"Unexpected error: {str(exc)}", exc_info=True)
        
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": "SERVER_ERROR",
                    "message": "An unexpected error occurred",
                    "details": {}
                },
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        )
