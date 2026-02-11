"""
Module api_return_handler.py
Part of the LCCN Harvester Project.
"""
from api.base_api import ApiResult
from . import lccn_validator, nlmcn_validator, call_number_normalizer

def normalize_api_result(result: ApiResult) -> ApiResult:
    """
    Normalize call numbers in an ApiResult based on source.
    """
    if result.status != "success":
        return result

    '''
    For testing we make each separate statement even though they run the same logic
    After testing has been done, then we could group them for simplicity.
    '''

    if result.source == "harvard":
        if result.lccn:
            result.lccn = call_number_normalizer.normalize_non_marc_call_number(result.lccn)
        if result.nlmcn:
            result.nlmcn = call_number_normalizer.normalize_non_marc_call_number(result.nlmcn)

    elif result.source == "openlibrary":
        if result.lccn:
            result.lccn = call_number_normalizer.normalize_non_marc_call_number(result.lccn)

    elif result.source == "loc":
        if result.lccn:
            result.lccn = call_number_normalizer.normalize_non_marc_call_number(result.lccn)
        if result.nlmcn:
            result.nlmcn = call_number_normalizer.normalize_non_marc_call_number(result.nlmcn)

    return validate_api_result(result)

def validate_api_result(result: ApiResult) -> ApiResult:
    """
    Validate normalized call numbers in an ApiResult.
    Invalid values are cleared (set to None).
    """
    if result.status != "success":
        return result

    if result.lccn and not lccn_validator.is_valid_lccn(result.lccn):
        result.lccn = None

    if result.nlmcn and not nlmcn_validator.is_valid_nlmcn(result.nlmcn):
        result.nlmcn = None

    return result
