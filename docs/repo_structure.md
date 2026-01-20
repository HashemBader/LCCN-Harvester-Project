This document describes the planned layout of the LCCN Harvester repository.
The goal is to keep files organized so the team and the client can easily find
code, tests, documentation, configuration, and sample data.

This structure is expected to stay stable at the top level. New subfolders may
be added in future sprints as new components are implemented.

Top-Level Layout:
LCCN-Harvester/
  src/              # Application source code
  tests/            # Automated tests
  docs/             # Project documentation
  data/             # Sample input/output data (non-secret)
  config/           # Configuration templates and example files

  init_project.py   # One-time project initialization script (if used)
  requirements.txt  # Python dependencies
  README.md         # Project overview and quick start
  LICENSE           # MIT license
  .gitignore        # Git ignore rules


src/ – Application Code (Here where all implementation code for the harvester lives under):
  harvester/        # Core harvesting pipeline and orchestration
  db/               # SQLite schema, migrations, and database access helpers
  apis/             # HTTP API clients (e.g., LOC, Harvard, OpenLibrary)
  z3950/            # Z39.50 client wrappers and utilities
  gui/              # PyQt6 graphical user interface
  util/             # Shared helpers (logging, config loading, common types)

Guidelines
New modules should be placed under the most appropriate subfolder above.
Shared helper functions that do not belong to a specific subsystem go in src/util/.
Z39.50-specific code should stay in src/z3950/ so it is easy to find and maintain.


tests/ – Automated Tests (All automated tests live under tests/, mirroring the structure of src/ as much as possible.)
  unit/             # Unit tests for individual functions/classes
  integration/      # Integration tests that exercise multiple components

Guidelines
For a module src/<area>/foo.py, unit tests should go in tests/unit/<area>/test_foo.py.
Integration tests that exercise the full pipeline or DB + API together go under tests/integration/.
Test runs and results are recorded in the separate testing log file.


docs/ – Documentation (Project documentation is stored in docs/).
  project_plan/             # CS4820 project plan sources (doc/figures)
  user_guide.md             # User manual for librarians
  technical_manual.md       # Technical manual for developers/maintainers
  dev_setup.md              # Environment setup instructions
  contribution_workflow.md  # Git contribution & branch workflow
  repo_structure.md         # This file: directory layout
  documentation_index.md    # Overview of all docs and how to update them
  testing_log.*             # Central testing log (spreadsheet or markdown)

Guidelines
Any change to the system design, architecture, or process should be reflected in the appropriate document under docs/.
Diagrams used in the project plan (use case, sequence, activity, etc.) are stored under docs/project_plan/ or a subfolder thereof.


data/ – Sample and Reference Data (contains non-sensitive sample files used during development, testing, and demonstrations).
  sample/           # Example ISBN input TSVs and sample MARC/JSON records
  reference/        # Reference files provided by the client or standards bodies

Guidelines
Do not store real patron data or any confidential information here.
Large generated outputs (e.g., exports created during testing) should either be placed under a temporary subfolder that is git-ignored or not committed at all.


config/ – Configuration Templates (The config/ folder contains configuration templates and example files thatdescribe how the harvester is set up).
  targets.example.tsv   # Example configuration of Z39.50/API targets
  settings.example.ini  # Example global settings (if needed)

Guidelines
Developers copy these example files to real config files (e.g., targets.tsv) in their local environment, which are git-ignored.
Any change to the expected configuration format should be reflected here.


Root Files

init_project.py
Optional script for one-time setup tasks (creating the database file, copying example configs, etc.), if used.
requirements.txt
List of Python packages needed to run the project.
README.md
High-level overview of the project and a pointer to docs/dev_setup.md and other documentation.
LICENSE
MIT license text for the project.
.gitignore
Ignore rules (e.g., virtual environments, __pycache__, local databases, generated logs/exports).
