"""
Module call_number_normalizer.py
Part of the LCCN Harvester Project.
"""


def normalize_call_number(subfield_a: list[str], subfield_b: list[str] | None = None) -> str:
    """
    Normalize MARC 050/060 call number from subfields.

    Per MARC 050/060 standards:
    - Use FIRST $a subfield if multiple exist
    - Concatenate with $b subfields, space-separated
    - Preserve spacing and punctuation within subfield values
    - Trim leading/trailing whitespace from result
    """
    if not subfield_a:
        return ""

    # Use FIRST $a if multiple exist
    a = subfield_a[0].strip()

    parts = [a]

    if subfield_b:
        b = " ".join(s.strip() for s in subfield_b if s.strip())
        if b:
            parts.append(b)

    return " ".join(parts)


def normalize_isbn_subfield(subfield_a_value: str | None) -> str:
    """
    Normalize MARC 020 $a ISBN content.

    - Trims surrounding whitespace using the shared normalizer utility style
    - Removes non ISBN characters (hyphens, spaces, punctuation)
    - Preserves digits and X checksum, uppercased
    """
    normalized = normalize_call_number([subfield_a_value or ""])
    if not normalized:
        return ""

    return "".join(ch.upper() for ch in normalized if ch.isdigit() or ch in "Xx")
