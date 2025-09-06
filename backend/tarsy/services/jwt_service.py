"""
JWT token generation and validation service.

Provides RSA-based JWT token management for user and service account authentication.
"""

from pathlib import Path
from typing import Any, Dict

import jwt
from cryptography.hazmat.primitives import serialization
from fastapi import HTTPException, status

from tarsy.config.settings import Settings
from tarsy.utils.timestamp import now_us


class JWTService:
    """JWT token generation and validation service."""
    
    def __init__(self, settings: Settings):
        """Initialize JWT service with settings and load RSA keys."""
        self.settings = settings
        self.algorithm = settings.jwt_algorithm
        self.issuer = settings.jwt_issuer
        
        # Load RSA keys
        private_key_path = Path(settings.jwt_private_key_path)
        public_key_path = Path(settings.jwt_public_key_path)
        
        if not private_key_path.exists():
            raise FileNotFoundError(f"JWT private key not found at {private_key_path}")
        if not public_key_path.exists():
            raise FileNotFoundError(f"JWT public key not found at {public_key_path}")
        
        with open(private_key_path, 'rb') as f:
            self.private_key = serialization.load_pem_private_key(
                f.read(), password=None
            )
            
        with open(public_key_path, 'rb') as f:
            self.public_key = serialization.load_pem_public_key(f.read())
    
    def create_user_jwt_token(
        self, 
        user_id: str, 
        username: str, 
        email: str, 
        avatar_url: str
    ) -> str:
        """Create JWT token for authenticated user."""
        now_us_timestamp = now_us()
        now_seconds = now_us_timestamp // 1_000_000  # Convert microseconds to seconds
        exp_seconds = now_seconds + (self.settings.user_token_expiry_hours * 3600)
        
        payload = {
            "sub": user_id,
            "username": username,
            "email": email,
            "avatar_url": avatar_url,
            "iss": self.issuer,
            "iat": int(now_seconds),
            "exp": int(exp_seconds)
        }
        
        return jwt.encode(payload, self.private_key, algorithm=self.algorithm)
    
    def create_service_account_jwt_token(self, service_name: str) -> str:
        """Create long-lived JWT token for service accounts."""
        now_us_timestamp = now_us()
        now_seconds = now_us_timestamp // 1_000_000  # Convert microseconds to seconds
        
        payload = {
            "sub": f"service_account:{service_name}",
            "service_account": True,
            "iss": self.issuer,
            "iat": int(now_seconds)
            # No expiration for service accounts
        }
        
        return jwt.encode(payload, self.private_key, algorithm=self.algorithm)
    
    def verify_jwt_token(self, token: str) -> Dict[str, Any]:
        """Verify and decode JWT token."""
        try:
            payload = jwt.decode(
                token, 
                self.public_key, 
                algorithms=[self.algorithm],
                issuer=self.issuer
            )
            return payload
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}"
            )
