# MARC $a and $b Extraction and Normalization Flow

## Quick Answer: Where the Code Extracts $a and $b

### Three Entry Points (Different Input Formats):

1. **MARC-JSON Format** → `src/utils/marc_parser.py:extract_marc_fields_from_json()`
   - Lines 37-94
   - Looks for `"a"` and `"b"` keys in subfield dictionaries

2. **MARCXML Format** → `src/utils/marc_parser.py:extract_marc_fields_from_xml()`
   - Lines 96-160
   - Looks for `code="a"` and `code="b"` attributes in XML subfield elements

3. **PyMARC Format** → `src/z3950/marc_decoder.py:_extract_subfields_from_pymarc_field()`
   - Lines 106-127
   - Looks for `.code == "a"` and `.code == "b"` in subfield namedtuples

### Then Normalizes with:

4. **Normalizer** → `src/utils/call_number_normalizer.py:normalize_call_number()`
   - Lines 1-31
   - Takes first $a only, appends all $b with spaces

### Then Validates with:

5. **Validator** → `src/utils/lccn_validator.py:is_valid_lccn()`
   - Lines 1-162
   - Checks if normalized result matches LC/NLM format rules

---

## Detailed Code Locations

### Location 1: MARC-JSON Extraction

**File:** `src/utils/marc_parser.py`  
**Lines:** 63-94  
**Function:** `extract_marc_fields_from_json()`

```python
# THE KEY PART (lines 75-90):
for field in fields:
    for tag in ("050", "060"):
        if tag in field:
            subfields = field[tag].get("subfields", [])
            for sf in subfields:
                if "a" in sf:                          # ← FINDS $a
                    text = sf["a"]
                    if isinstance(text, str):
                        result[tag]["a"].append(text.strip())
                elif "b" in sf:                        # ← FINDS $b
                    text = sf["b"]
                    if isinstance(text, str):
                        result[tag]["b"].append(text.strip())
```

**What it does:**
- Iterates through all fields in the MARC record
- For fields tagged "050" (LCCN) or "060" (NLM)
- Looks at the `subfields` array
- Checks each subfield dict for keys "a" or "b"
- Strips whitespace and collects values into lists

**Input example:**
```json
{
  "fields": [
    {
      "050": {
        "subfields": [
          {"a": "HF5726"},
          {"b": ".B27 1980"}
        ]
      }
    }
  ]
}
```

**Output:**
```python
{
  "050": {
    "a": ["HF5726"],        # All $a values
    "b": [".B27 1980"]      # All $b values
  }
}
```

---

### Location 2: MARCXML Extraction

**File:** `src/utils/marc_parser.py`  
**Lines:** 96-160  
**Function:** `extract_marc_fields_from_xml()`

```python
# THE KEY PART (lines 118-135):
for field in datafields:
    tag = field.get("tag")
    if tag in ("050", "060"):
        for subfield in field.findall("marc:subfield", namespaces):
            code = subfield.get("code")    # ← GETS SUBFIELD CODE ("a", "b", etc.)
            text = subfield.text
            
            if code == "a":                # ← CHECKS IF IT'S $a
                result[tag]["a"].append(text.strip())
            elif code == "b":              # ← CHECKS IF IT'S $b
                result[tag]["b"].append(text.strip())
```

**What it does:**
- Iterates through all datafield elements in MARCXML
- For fields with tag "050" or "060"
- Looks at each subfield child element
- Checks the `code` attribute ("a", "b", "c", etc.)
- Strips whitespace and collects values into lists

**Input example:**
```xml
<datafield tag="050" ind1="1" ind2="0">
  <subfield code="a">HF5726</subfield>      ← $a
  <subfield code="b">.B27 1980</subfield>   ← $b
</datafield>
```

**Output:**
```python
{
  "050": {
    "a": ["HF5726"],
    "b": [".B27 1980"]
  }
}
```

---

### Location 3: PyMARC Extraction (Z39.50)

**File:** `src/z3950/marc_decoder.py`  
**Lines:** 106-127  
**Function:** `_extract_subfields_from_pymarc_field()`

```python
# THE KEY PART (lines 112-120):
if hasattr(field, 'subfields'):
    for sf in field.subfields:
        code = sf.code          # ← GETS SUBFIELD CODE FROM NAMEDTUPLE
        value = sf.value
        if code and value:
            subfields_list.append({code: value.strip()})
            # Results in: [{"a": "value"}, {"b": "value"}]
```

**What it does:**
- Iterates through subfields in a pymarc Field object
- Each subfield is a namedtuple with `.code` and `.value`
- Extracts code (e.g., "a", "b") and value
- Returns list of dicts: `[{"a": "..."}, {"b": "..."}]`

**Input example:**
```python
Field("050", indicators=[" ", "1"],
  subfields=[
    Subfield(code="a", value="HF5726"),
    Subfield(code="b", value=".B27 1980")
  ]
)
```

**Output:**
```python
[
  {"a": "HF5726"},
  {"b": ".B27 1980"}
]
```

---

### Location 4: Normalization (Combines $a and $b with Space)

**File:** `src/utils/call_number_normalizer.py`  
**Lines:** 7-31  
**Function:** `normalize_call_number()`

```python
# THE KEY PART (lines 17-30):
def normalize_call_number(subfield_a: list[str], subfield_b: list[str] | None = None) -> str:
    if not subfield_a:
        return ""
    
    # Use FIRST $a if multiple exist
    a = subfield_a[0].strip()              # ← TAKES FIRST $a ONLY
    
    parts = [a]
    
    if subfield_b:
        # Join all $b values with spaces
        b = " ".join(s.strip() for s in subfield_b if s.strip())
        if b:
            parts.append(b)                # ← APPENDS ALL $b
    
    return " ".join(parts)                 # ← JOINS WITH SPACE
```

**What it does:**
1. Takes the **FIRST** `$a` value (ignores extras)
2. Joins **ALL** `$b` values with spaces
3. Combines them with a space separator
4. Result: `$a $b1 $b2 ...`

**Examples:**

| Input | Output |
|-------|--------|
| `a=["HF5726"], b=[".B27", "1980"]` | `"HF5726 .B27 1980"` |
| `a=["Z7164.N3", "Z7165.R42"], b=["L34 no. 9"]` | `"Z7164.N3 L34 no. 9"` |
| `a=["QA76.73"], b=[]` | `"QA76.73"` |

---

### Location 5: Validation (Checks if Normalized Result is Valid)

**File:** `src/utils/lccn_validator.py`  
**Lines:** 1-162  
**Function:** `is_valid_lccn()`

```python
# THE KEY PART (lines 28-30):
# Split into space-separated components
parts = call_number.split()  # ← SPLITS ON SPACES

# Part 1: Class (letters + numbers, possibly with decimal)
class_part = parts[0]        # ← FIRST PART IS THE CLASS
```

**What it does:**
1. Takes the normalized call number (e.g., `"HF5726 .B27 1980"`)
2. Splits on spaces: `["HF5726", ".B27", "1980"]`
3. Validates first part is valid LC class (1-3 letters + 1-4 digits)
4. Validates remaining parts are cutters or years
5. Returns True/False

**Validation rules checked:**
- Class must have 1-3 letters (excluding I and O)
- Class must have 1-4 digits after letters
- Can have decimal part: `.73`, `.P38`, etc.
- Can have cutter: `.P38`, `.B27`
- Can have year: `1980`, `2005`

---

## Complete Example Walk-Through

### Input: MARC Record with Multiple $a and $b

```
MARC Binary Data:
  050 10$aZ7164.N3$bL34 no. 9$aZ7165.R42$aHC517.R42
        ^a field  ^b field ^a field  ^a field
```

### Step 1: Extract (Identify All $a and $b)

**If MARC-JSON format:**
```json
{
  "fields": [
    {
      "050": {
        "subfields": [
          {"a": "Z7164.N3"},
          {"b": "L34 no. 9"},
          {"a": "Z7165.R42"},
          {"a": "HC517.R42"}
        ]
      }
    }
  ]
}
```

**After extraction:**
```python
{
  "050": {
    "a": ["Z7164.N3", "Z7165.R42", "HC517.R42"],  # All $a found
    "b": ["L34 no. 9"]                             # All $b found
  }
}
```

### Step 2: Normalize (Use First $a, All $b)

```python
normalize_call_number(
  subfield_a=["Z7164.N3", "Z7165.R42", "HC517.R42"],
  subfield_b=["L34 no. 9"]
)
```

**Inside normalize function:**
```python
a = subfield_a[0].strip()          # Takes FIRST: "Z7164.N3"
b = " ".join(["L34 no. 9"])        # Joins all $b: "L34 no. 9"
return " ".join([a, b])            # Combines: "Z7164.N3 L34 no. 9"
```

**Result:** `"Z7164.N3 L34 no. 9"`

### Step 3: Validate

```python
is_valid_lccn("Z7164.N3 L34 no. 9")

parts = "Z7164.N3 L34 no. 9".split()
       = ["Z7164.N3", "L34", "no.", "9"]

class_part = "Z7164.N3"
# Check: Z (1 letter) ✓, 7164 (4 digits) ✓, .N3 (decimal cutter) ✓

remaining = ["L34", "no.", "9"]
# Check: L34 (cutter format) ✓, "no." ✓, "9" ✓

Result: VALID ✓
```

---

## Summary

| Step | Where | What | Input | Output |
|------|-------|------|-------|--------|
| **Extract** | `marc_parser.py` | Find all $a and $b in field | Raw MARC | Lists: `a=[], b=[]` |
| **Normalize** | `call_number_normalizer.py` | Combine $a[0] + all $b with spaces | Lists | String: `$a $b ...` |
| **Validate** | `lccn_validator.py` | Check if format is valid | String | Boolean: True/False |

The key point: **The extraction, normalization, and validation all work together to implement your requirement:**

> "Use first $a, replace $b with space, and validate the result"

