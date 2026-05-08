"""Domain-level errors raised by services (map to HTTP in routes)."""


class EmailAlreadyRegisteredError(Exception):
    """Registration attempted with an email that already exists."""


class InvalidCredentialsError(Exception):
    """Login failed due to unknown email or wrong password."""
