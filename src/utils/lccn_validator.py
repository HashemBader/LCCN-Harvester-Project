"""
Module: lccn_validator.py
Part of the LCCN Harvester Project.
"""

def validate_lccn(raw_lccn):
    # 1. Clean and normalize (e.g., '2001-123' -> '2001000123')
    clean=raw_lccn.strip().replace(" ", "")

    if "-" in clean:
        year, serial=clean.split("-")
        normalized=year + serial.zfill(6)
    else:
        normalized=clean

    # 2. Extract parts
    digits="".join(c for c in normalized if c.isdigit())
    alpha="".join(c for c in normalized if c.isalpha())

    # 3. Check structural rules
    is_numeric_correct=len(digits) in [8, 10]
    is_prefix_correct=len(alpha) <= 3 and (not alpha or alpha.islower())

    # Valid if numeric length is 8/10 AND prefix is valid lowercase letters
    return normalized, (is_numeric_correct and is_prefix_correct)


# Test it
lccn, is_valid=validate_lccn("2001-123")
print(f"LCCN: {lccn}, Valid: {is_valid}")
