#!/usr/bin/env python3
"""
JWT Token Generator for Tarsy API Authentication
Usage: python generate_token.py [days] [private_key_path] [subject] [issuer]

Default private_key_path: config/keys/jwt_private_key.pem (project root)
"""

import datetime
import sys
from pathlib import Path

import jwt


def _load_private_key(private_key_path: Path) -> str:
    """Load private key from file.
    
    Args:
        private_key_path: Path to the JWT private key file
        
    Returns:
        Private key content as string
        
    Raises:
        FileNotFoundError: If the private key file doesn't exist
        PermissionError: If there are insufficient permissions to read the file
        OSError: If there are other OS-level issues reading the file
    """
    if not private_key_path.exists():
        raise FileNotFoundError(f"Private key file not found at {private_key_path}. Run 'make generate-jwt-keys' first")
    
    try:
        with open(private_key_path, 'r') as f:
            return f.read()
    except (FileNotFoundError, PermissionError, OSError) as e:
        raise type(e)(f"Unable to read private key at {private_key_path}: {e}") from e


def generate_jwt_token(private_key_path: Path, expiration_days: int = 30, subject: str = "monitoring-system", issuer: str = "http://localhost:8000") -> str:
    """Generate a JWT token for API authentication.
    
    Args:
        private_key_path: Path to the JWT private key file
        expiration_days: Number of days until token expires (default: 30)
        subject: Subject claim for the token (default: "monitoring-system")
        issuer: Issuer claim for the token (default: "http://localhost:8000")
        
    Returns:
        Encoded JWT token string
        
    Raises:
        FileNotFoundError: If the private key file doesn't exist
        PermissionError: If there are insufficient permissions to read the file
        OSError: If there are other OS-level issues reading the file
    """
    # Load the private key
    private_key = _load_private_key(private_key_path)
    
    # Create JWT payload
    now_utc = datetime.datetime.now(datetime.UTC)
    payload = {
        'iss': issuer,                # Issuer (must be a valid URL for oauth2-proxy, where the issuer URL has a .well-known/openid-configuration or a .well-known/jwks.json)
        'aud': 'tarsy-api',           # Audience
        'sub': subject,               # Subject (configurable)
        'exp': now_utc + datetime.timedelta(days=expiration_days),
        'iat': now_utc,               # Issued at
        'scope': 'api:read api:write' # Scopes
    }
    
    # Generate token with RS256 algorithm
    token = jwt.encode(
        payload, 
        private_key, 
        algorithm='RS256', 
        headers={'kid': 'tarsy-api-key-1'}  # Key ID matching JWKS endpoint
    )
    return token


def main() -> None:
    """Main function."""
    # Parse command line arguments
    expiration_days = 30  # Default
    # Default: Use config/keys/jwt_private_key.pem in project root
    project_root = Path(__file__).parent.parent  # backend/ -> project root
    private_key_path = project_root / "config/keys/jwt_private_key.pem"
    subject = "monitoring-system"  # Default
    issuer = "http://localhost:8000"  # Default
    
    if len(sys.argv) > 1:
        try:
            expiration_days = int(sys.argv[1])
            if expiration_days <= 0:
                raise ValueError("Expiration days must be positive")
        except ValueError as e:
            print(f"Error: {e}")
            print("Usage: python generate_token.py [days] [private_key_path] [subject] [issuer]")
            sys.exit(1)
    
    if len(sys.argv) > 2 and sys.argv[2].strip():
        private_key_path = Path(sys.argv[2])
    
    if len(sys.argv) > 3 and sys.argv[3].strip():
        subject = sys.argv[3]
    
    if len(sys.argv) > 4 and sys.argv[4].strip():
        issuer = sys.argv[4]
    
    # Resolve relative paths from current working directory
    if not private_key_path.is_absolute():
        private_key_path = private_key_path.resolve()
    
    # Generate and print token
    try:
        token = generate_jwt_token(private_key_path, expiration_days, subject, issuer)
        print(f"Generated JWT token for '{subject}' from issuer '{issuer}' (expires in {expiration_days} days):")
        print(token)
    except (FileNotFoundError, PermissionError, OSError) as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error generating token: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
