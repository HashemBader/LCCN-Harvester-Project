# Documentation Index

This folder holds the project documentation. Most files come straight from the project plan (scope, requirements, use cases, features, delivery plan, risks, charts/diagrams). The rest are short build/use guides so someone can actually run and test the app.

---

## Overview
High-level project context and stakeholders.

- [overview/vision.md](overview/vision.md) — What the tool does and the main goal
- [overview/scope.md](overview/scope.md) — In-scope vs out-of-scope features
- [overview/community.md](overview/community.md) — Client, team roles, and coordination

---

## Requirements
Functional and non-functional requirements.

- [requirements/key_requirements.md](requirements/key_requirements.md) — Technical and operational requirements
- [requirements/acceptance_tests.md](requirements/acceptance_tests.md) — Acceptance tests (definition of done)

---

## Use Cases
User actions and system responses.

- [use-cases/use_cases.md](use-cases/use_cases.md) — U01–U19 use cases

---

## Features
Implementation checklist and priorities.

- [feature-list/feature_list.md](feature-list/feature_list.md) — F01–F09 features with acceptance criteria

---

## Architecture
Technical design and internal structure.

- [architecture/database_architecture.md](architecture/database_architecture.md) — Database schema, tables, and data pipeline
- [architecture/database_schema.md](architecture/database_schema.md) — SQLite table definitions
- [architecture/harvest_pipeline.md](architecture/harvest_pipeline.md) — End-to-end harvesting workflow
- [architecture/normalization_rules.md](architecture/normalization_rules.md) — ISBN, LCCN, NLMCN parsing rules

---

## Configuration
Settings and target management.

- [configuration/config_overview.md](configuration/config_overview.md) — Where configuration lives
- [configuration/targets_tsv_format.md](configuration/targets_tsv_format.md) — Targets file schema

---

## Research
Technical research and feasibility analysis.

- [research/loc_api.md](research/loc_api.md) — Library of Congress API
- [research/harvard_librarycloud_api.md](research/harvard_librarycloud_api.md) — Harvard LibraryCloud API
- [research/openlibrary_api.md](research/openlibrary_api.md) — OpenLibrary API
- [research/z3950_protocol.md](research/z3950_protocol.md) — Z39.50 protocol overview
- [research/z3950_python_libraries.md](research/z3950_python_libraries.md) — Python Z39.50 library evaluation
- [research/marc_isbn_lccn_nlmcn_standards.md](research/marc_isbn_lccn_nlmcn_standards.md) — MARC field standards
- [z_3950_yaz_feasibility.md](z_3950_yaz_feasibility.md) — YAZ translation feasibility analysis

---

## Testing
Test strategy and verification.

- [testing/test_plan.md](testing/test_plan.md) — Testing strategy and acceptance mapping

---

## Developer Guides
Setup, standards, and workflow.

- [environment_setup.md](environment_setup.md) — Environment setup (venv, deps, run)
- [coding_standards.md](coding_standards.md) — Naming conventions, constraints, style
- [contribution_workflow.md](contribution_workflow.md) — Git workflow and branch strategy
- [repo_structure.md](repo_structure.md) — Repository directory layout
- [translation.md](translation.md) — C-to-Python translation conventions

---

## Release
User-facing guides and release process.

- [release/cli_user_guide.md](release/cli_user_guide.md) — CLI usage guide (current)
- [release/user_guide.md](release/user_guide.md) — Client-facing usage guide
- [release/installation_guide.md](release/installation_guide.md) — Installation instructions
- [release/technical_documentation.md](release/technical_documentation.md) — Developer-facing architecture overview
- [release/release_checklist.md](release/release_checklist.md) — Final packaging checklist