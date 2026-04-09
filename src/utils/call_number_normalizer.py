"""
call_number_normalizer.py

Low-level assembly and normalisation of MARC subfield values.

Responsibilities
----------------
- ``normalize_call_number`` — assembles a MARC 050 (LC Classification) or
  060 (NLM Classification) call number string from its parsed ``$a`` and
  ``$b`` subfields, following MARC field construction rules.
- ``normalize_isbn_subfield`` — strips non-digit/non-checksum characters
  from a MARC 020 ``$a`` subfield to produce a bare ISBN digit string.

These functions operate purely on pre-extracted subfield lists; they do NOT
parse raw XML or validate formats.  Validation is handled by the dedicated
validator modules (lccn_validator, nlmcn_validator, isbn_validator).

Part of the LCCN Harvester Project.
"""


def normalize_call_number(subfield_a: list[str], subfield_b: list[str] | None = None) -> str:
    """
    Assemble a normalized MARC 050/060 call number from subfield lists.

    MARC 050 (LC Classification) and 060 (NLM Classification) fields can
    contain multiple ``$a`` and ``$b`` subfields.  The standard assembly rule
    is: take only the **first** ``$a``, then append all ``$b`` values
    space-separated.  This produces a string like ``"QA76.73 .P38"`` from
    ``$a="QA76.73"`` and ``$b=".P38"``.

    Parameters
    ----------
    subfield_a : list[str]
        All ``$a`` subfield values extracted from the MARC field.  Only the
        first element is used (repeated ``$a`` subfields are ignored per MARC
        cataloguing practice).
    subfield_b : list[str] | None
        All ``$b`` subfield values (Cutter number / item portion).  All
        elements are joined with a single space.  Pass ``None`` or ``[]`` for
        fields that have no ``$b``.

    Returns
    -------
    str
        Assembled and whitespace-trimmed call number, or ``""`` if
        ``subfield_a`` is empty or blank.
    """
    if not subfield_a:
        return ""

    # MARC rule: when multiple $a subfields exist, only the first is used for
    # the classification notation.
    a = subfield_a[0].strip()

    parts = [a]

    if subfield_b:
        # Join all $b subfields with a space; skip any that are blank after stripping.
        b = " ".join(s.strip() for s in subfield_b if s.strip())
        if b:
            parts.append(b)

    return " ".join(parts)


def normalize_isbn_subfield(subfield_a_value: str | None) -> str:
    """
    Normalize a MARC 020 ``$a`` subfield value to a bare ISBN digit string.

    MARC 020 ``$a`` often contains qualifying text after the ISBN digits,
    for example ``"0201633612 (acid-free paper)"``.  This function strips
    everything except the ISBN digits and the ``X`` check character.

    Parameters
    ----------
    subfield_a_value : str | None
        Raw ``$a`` subfield text from a MARC 020 field.  ``None`` is treated
        as an empty string.

    Returns
    -------
    str
        Uppercased string containing only digits and ``X``, or ``""`` if the
        input is blank.
    """
    # Re-use normalize_call_number for consistent whitespace trimming.
    normalized = normalize_call_number([subfield_a_value or ""])
    if not normalized:
        return ""

    # Keep only characters that are valid in an ISBN: digits 0-9 and the
    # check character X (used as the ISBN-10 check digit for value 10).
    return "".join(ch.upper() for ch in normalized if ch.isdigit() or ch in "Xx")
