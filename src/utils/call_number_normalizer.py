"""
Module call_number_normalizer.py
Part of the LCCN Harvester Project.
"""


def normalize_marc_call_number(subfield_a: list[str], subfield_b: list[str] | None = None) -> str:
    """
    Normalize MARC 050/060 call number from subfields.
    """
    if not subfield_a:
        return ""

    # Use last $a if multiple exist
    a = subfield_a[-1].strip()

    parts = [a]

    if subfield_b:
        b = " ".join(s.strip() for s in subfield_b if s.strip())
        if b:
            parts.append(b)

    return " ".join(parts)

def normalize_non_marc_call_number(raw: str) -> str:
    """
    Normalize a call number string returned from an API
    that does not use MARC 050/060 call numbers.
    """
    if not raw:
        return ""

    # Normalize spacing
    parts = raw.strip().split()
    return " ".join(parts)

