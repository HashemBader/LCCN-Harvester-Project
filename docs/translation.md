# translation.md

## Purpose
Defines the translation rules and conventions the team will follow if any existing C-based logic (e.g., Z39.50/YAZ client behavior) needs to be translated into Python 3 for this project. The harvester must be entirely in Python (no C code may be used), and it must remain cross-platform (Windows/Mac/Linux).

## Context / scope
- The main translation risk area is C-based YAZ Z39.50 client logic (or similar protocol/client behavior) since the project must still support Z39.50 while remaining Python-only.
- If the team decides to write Z39.50 from scratch, this document still applies to any “translated-style” components (protocol parsing, record decoding, etc.) to keep consistency.

---

## What belongs here

### 1) Naming conventions for translated functions/classes
Goal: keep translated code readable and Pythonic, while preserving traceability to the original logic when needed.

Rules
- Use snake_case for functions/variables and PascalCase for classes.
- Prefer descriptive names over literal C identifiers.
- When a name maps directly to a known protocol concept, use the protocol term consistently (session, target, timeout, record_retrieval).
- If you need traceability to C identifiers, add it in a docstring tag (not in the name).

Examples
```py
class Z3950Session:
    """C-origin: ZSESSION (conceptual mapping)"""

def parse_marc_record(raw_bytes: bytes) -> dict:
    """C-origin: yaz_marc_decode() (conceptual mapping)"""
```

File organization
- Keep translated/protocol code isolated from GUI:
  - z3950/ (session, connection, request/response)
  - marc/ (record decoding, field/subfield extraction)
  - core/ (normalization, validation)
  - gui/ remains UI-only

---

### 2) Mapping structs/enums to Python equivalents
Goal: replace C data structures with clear Python types that are testable and easy to validate.

Structs → @dataclass
- Any C “struct-like” group of fields becomes a dataclass.
- Use type hints everywhere.
- Provide a validate() method for critical config objects (targets, timeouts, etc.).

Example
```py
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class TargetConfig:
    name: str
    kind: str  # "api" or "z3950"
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    selected: bool = True
    rank: int = 0

    def validate(self) -> None:
        if self.kind == "z3950":
            if not self.host or not self.port or not self.database:
                raise ValueError("Z39.50 target must include host/port/database")
```

Enums → enum.Enum
- Use Python Enum for fixed choice sets (status codes, result types, error categories).
- Keep enum names stable and used across the codebase.

Buffers/byte arrays
- Prefer bytes for immutable network payloads and bytearray for mutable buffers.
- Never assume null-termination; always track lengths explicitly.

Pointers / ownership
- Any C pointer ownership patterns become explicit in Python:
  - “Caller owns memory” → caller creates objects; callee returns new objects without side effects.
  - “C frees memory” → in Python rely on GC, but ensure resources are handled via context managers for sockets/files.

---

### 3) Error-handling conventions (exceptions vs return objects)
Goal: predictable behavior under network issues and malformed data, without freezing the app.

Core rule
- Use exceptions for programmer/config errors and unexpected runtime failures.
- Use return objects for normal “no match / not found / skipped” outcomes.

Suggested pattern
```py
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class LookupResult:
    found: bool
    isbn: str
    lccn: Optional[str] = None
    nlmcn: Optional[str] = None
    source: Optional[str] = None
    error: Optional[str] = None  # for non-fatal issues (timeout, no record, etc.)
```

When to raise exceptions
- Invalid target configuration (missing host/port/db)
- Internal parsing bug (unexpected MARC structure indicating a coding issue)
- Database connection failure that prevents operation

When to return “not found”
- No record found on a target
- Target skipped due to retry-days logic
- Target timeout (return found=False + error="timeout" and also log/record failure)

Failure recording alignment
- Any non-found due to a target attempt should be recorded in the Attempted table (ISBN, target attempted, date attempted) as defined in the project design.

---

### 4) Logging conventions
Goal: consistent, searchable logs for debugging and client support.

Rules
- Use Python logging (no prints in production code).
- Don’t log full MARC payloads by default. Log summaries and IDs.
- Log at these levels:
  - DEBUG: request/response summaries, parsing steps, retry decisions
  - INFO: normal lifecycle events (start/stop harvest, target order)
  - WARNING: timeouts, temporary network failures, skipped targets
  - ERROR: unexpected exceptions, corrupted data handling

Minimum fields per event
- isbn (normalized)
- target (API/Z39.50 name)
- stage (cache_check / attempted_check / api_lookup / z3950_lookup / parse / normalize / db_write)
- result (found/not_found/timeout/error)

Example
```py
logger.info("lookup_complete", extra={
    "isbn": isbn,
    "target": target_name,
    "stage": "z3950_lookup",
    "result": "timeout",
})
```

---

### 5) Do / don’t rules for consistent translated code

Do
- Keep everything Python 3 only and compatible with PyQt6 GUI integration.
- Use explicit timeouts for network calls (Z39.50 especially) to prevent UI freezes.
- Normalize ISBNs by removing hyphens and keeping as text (don’t drop leading zeros).
- Follow call-number parsing rules when handling MARC:
  - 050 (LCCN): first $a, replace $b with a space
  - 060 (NLMCN): first $a, replace $b with a space

Don’t
- Don’t paste or reuse any C code directly (even if available).
- Don’t block the GUI thread with network calls; long tasks must run outside the UI event loop.
- Don’t silently swallow exceptions; either log + return a structured failure or raise with a clear message.
- Don’t introduce C-style global state; use scoped managers (session manager, DB manager).

---

### 6) Translation checklist (use during implementation)
- Identify the smallest behavior slice to port (connect + search + retrieve record).
- Define Python dataclasses/enums for inputs/outputs.
- Implement with timeouts + structured failures (record Attempted failures when appropriate).
- Add unit tests for parsing/normalization (especially MARC 050/060 logic).
- Verify cross-platform behavior (Windows/Mac/Linux).
- Verify “stop on find” behavior and target order logic remain correct.
