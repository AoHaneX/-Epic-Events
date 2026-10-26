"""Services métier du CRM."""


class BusinessError(ValueError):
    """Expected business validation failure."""


def validate_identifier(value, error_type=BusinessError):
    """Reject invalid identifiers before querying the database."""
    if type(value) is not int or value <= 0:
        raise error_type("L'identifiant doit être un entier strictement positif.")
