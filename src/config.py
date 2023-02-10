"""
Defines configuration objects for the Flask server.
"""

# =============================================================================

__all__ = ("get_config",)

# =============================================================================


class Config:
    """The base config object."""

    DEBUG = False
    DEVELOPMENT = False


class ProdConfig(Config):
    """The config object for production."""


class DevConfig(Config):
    """The config object for development."""

    DEBUG = True
    DEVELOPMENT = True


# =============================================================================


def get_config(debug=False):
    if debug:
        print("Debug is enabled: using DevConfig")
        return DevConfig
    print("Debug is disabled: using ProdConfig")
    return ProdConfig
