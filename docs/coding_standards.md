Coding Standards:

1. Core Constraints

* Python Only: Use Python 3.x only. C/C++ extensions or compiled binaries are explicitly prohibited.
* GUI Framework: Must use PyQt6.
* Z39.50 Implementation: Logic must be native Python or translated from C. You may not use compiled YAZ binaries or wrappers that require C compilation.
* License: All code must be compatible with the MIT Open Source License.

2. Naming Conventions

* Variables & Functions: snake_case (e.g., search_isbn, parse_response).
* Classes: PascalCase (e.g., DatabaseManager, LocAPI).
* Constants: UPPER_CASE (e.g., DEFAULT_RETRY_DAYS, MAX_TIMEOUT).
* Directories & Files: snake_case (e.g., src/, main.py).

3. Data Handling

* ISBNs: Always store and manipulate ISBNs as Strings/Text. Never use Integers, as this strips leading zeros (e.g., "0123..." becomes "123...").
* LCCN Parsing:
  - Extract the first $a subfield.
  - Replace the $b subfield with a space.
  - Remove trailing periods unless part of the classification.
* Database: Use SQLite for local storage. Never commit .db or .sqlite files to the repository.

4. Documentation

* Docstrings: Required for all classes and public functions. Must describe the Purpose, Arguments, and Return Values.
* Clean Code: Remove all debug print() statements before pushing code. Use a proper logging module if output is needed.
* Translation Notes: If translating C code (e.g., from the YAZ library) to Python, document the original source logic clearly in comments.

5. Directory Structure

Maintain the following structure to ensure the project remains navigable: