# Z39.50 YAZ Feasibility Analysis

## Purpose of This Document
This document explains why directly translating the YAZ (Yet Another Z39.50) toolkit from C into Python 3 is **not the best approach** for this project, and why implementing a **pure‑Python Z39.50 client** is both **faster** and **more feasible** given the project constraints.

The analysis covers:
- What YAZ provides
- How YAZ is normally used
- Possible ways to use YAZ from Python 3
- Risks and complexity of each option
- A recommended approach for the project

---

## What YAZ Provides

YAZ is an open‑source toolkit written in **C** that implements:

- Z39.50 client and server protocol stack (ISO 23950)
- ASN.1 definitions and BER encoding/decoding
- Support for related protocols (SRU/SRW, CQL, etc.)
- Command‑line tools such as `yaz-client`

YAZ is a **large, mature, and highly optimized** codebase that has evolved over many years and is intended primarily for **C/C++ system‑level development**.

---

## How YAZ Is Normally Used

YAZ is typically used in one of the following ways:

1. **C or C++ applications** directly linking against YAZ libraries
2. **Command‑line tools** (e.g., `yaz-client`) for manual querying and testing
3. **Server‑side integrations** where performance and low‑level control are critical

YAZ is **not designed as a Python‑native library**, and Python usage is not its primary use case.

---

## Options for Using YAZ from Python 3

### Option 1: Translate YAZ C Code into Python

**Description:**
Manually convert YAZ’s C source code into Python 3.

**Issues:**
- YAZ consists of **hundreds of source files** across many directories
- Core Z39.50 logic is deeply intertwined with:
  - ASN.1 encoding
  - Memory management
  - Network I/O
- Identifying where specific protocol behaviors are implemented is time‑consuming
- C‑style architecture does not map cleanly to Python

**Risks:**
- Extremely time‑consuming
- High risk of bugs and incomplete coverage
- Difficult to test and maintain
- Violates the spirit of rapid prototyping

**Conclusion:** ❌ Not practical or efficient

---

### Option 2: Use YAZ via Python Bindings or Wrappers

**Description:**
Use existing Python bindings, C extensions, or `ctypes` to call YAZ functions.

**Issues:**
- Still relies on **C code**, which is disallowed by project constraints
- Requires compiling native libraries
- Platform‑specific issues
- Harder to deploy and grade

**Risks:**
- Breaks the requirement of an **entirely Python** harvester
- Increases setup and compatibility issues

**Conclusion:** ❌ Not allowed for this project

---

### Option 3: Re‑implement Z39.50 in Pure Python (Recommended)

**Description:**
Implement a minimal Z39.50 client in Python 3 using:
- Python sockets
- Python ASN.1 libraries (e.g., `pyasn1`)
- Official Z39.50 (ISO 23950) specifications

**Advantages:**
- Fully compliant with project requirements
- Focuses only on **needed functionality** (Init, Search, Present)
- Avoids unnecessary YAZ complexity
- Faster to implement and debug
- Easier to understand, document, and maintain

**Risks:**
- Requires understanding ASN.1 and BER encoding
- Limited feature set compared to YAZ (acceptable for project scope)

**Conclusion:** ✅ Best balance of speed, clarity, and compliance

---

## Why Translating YAZ Is Slower, Not Faster

Although YAZ already exists, translating it is **slower** because:

- The codebase is **large and fragmented** across many folders
- Protocol logic is not isolated in a single location
- Considerable time would be spent simply locating where behaviors occur
- Python does not benefit from C‑level optimizations in a translation
- Much of YAZ’s functionality is **outside the project’s scope**

A smaller, purpose‑built Python implementation avoids all of these issues.

---

## Recommended Approach

The recommended approach for this project is to:

1. Use the **Z39.50 standard documentation** as the primary reference
2. Observe YAZ behavior only at a **conceptual level** (no code reuse)
3. Implement a **minimal Z39.50 client in Python 3** supporting:
   - InitRequest / InitResponse
   - SearchRequest / SearchResponse
   - PresentRequest / record retrieval
4. Use Python ASN.1 libraries for BER encoding/decoding

This approach is:
- Faster to complete
- Easier to justify academically
- Fully compliant with the requirement that the harvester be **entirely in Python**

---

## Final Justification Statement (for reports)

> Although the YAZ toolkit provides a complete Z39.50 implementation in C, its size, complexity, and architecture make direct translation to Python impractical and time‑consuming. This project therefore reimplements the required Z39.50 client functionality directly in Python 3 using the ISO 23950 specification, resulting in a simpler, faster, and fully compliant solution.

---

*End of document*

