"""Authentication module for P-Art web UI."""

import os
import secrets
from functools import wraps
from flask import request, Response
from werkzeug.security import check_password_hash, generate_password_hash


class AuthManager:
    """Simple authentication manager for P-Art web UI."""

    def __init__(self, enabled: bool = False, username: str = "admin", password: str = ""):
        self.enabled = enabled
        self.username = username
        # Store hashed password
        self.password_hash = generate_password_hash(password) if password else None

    def check_auth(self, username: str, password: str) -> bool:
        """Check if username/password is valid."""
        if not self.enabled:
            return True

        if not self.password_hash:
            return False

        return username == self.username and check_password_hash(self.password_hash, password)

    def authenticate(self):
        """Send 401 response that enables basic auth."""
        return Response(
            'Authentication required.\n'
            'Please provide valid credentials.',
            401,
            {'WWW-Authenticate': 'Basic realm="P-Art Login Required"'}
        )

    def requires_auth(self, f):
        """Decorator for routes that require authentication."""
        @wraps(f)
        def decorated(*args, **kwargs):
            if not self.enabled:
                return f(*args, **kwargs)

            auth = request.authorization
            if not auth or not self.check_auth(auth.username, auth.password):
                return self.authenticate()
            return f(*args, **kwargs)
        return decorated


def generate_random_password(length: int = 16) -> str:
    """Generate a secure random password."""
    return secrets.token_urlsafe(length)
