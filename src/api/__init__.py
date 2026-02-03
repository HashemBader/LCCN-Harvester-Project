"""
api package for the LCCN Harvester Project.
"""

from .base_api import ApiResult, BaseApiClient

__all__ = ["ApiResult", "BaseApiClient"]

from .loc_api import LocApiClient

__all__ = ["ApiResult", "BaseApiClient", "LocApiClient"]
