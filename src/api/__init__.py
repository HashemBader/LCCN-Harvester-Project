"""
api package for the LCCN Harvester Project.
"""

# Import core base classes used by all API clients
from .base_api import ApiResult, BaseApiClient

# Expose the base classes as part of the public API
__all__ = ["ApiResult", "BaseApiClient"]

# Import the Library of Congress API client implementation
from .loc_api import LocApiClient

# Add LocApiClient to the public API exports
__all__ = ["ApiResult", "BaseApiClient", "LocApiClient"]
