class CkaError(Exception):
    """An expected, user-facing failure. The CLI prints the message without a traceback."""


class SafetyError(CkaError):
    """Refusing an operation because the target is not a cka-managed environment."""
