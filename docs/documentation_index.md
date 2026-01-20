# docs index:

This folder holds the project documentation. Most files come straight from the project plan (scope, requirements, use cases, features, delivery plan, risks, charts/diagrams). The rest are short build/use guides so someone can actually run and test the app.

----------------------------------------------------------------------------------------------
Overview (what this project is)
- docs/00_overview/vision_statement.md — What the tool does, the main goal, and the expected outputs at a high level.
- docs/00_overview/statement_of_scope.md — What’s in scope vs out of scope, major assumptions, and constraints (platform, tech, etc.).
- docs/00_overview/project_community.md — Client/users, team roles, and any coordination notes that affect delivery.

----------------------------------------------------------------------------------------------
Requirements (what it must satisfy)
- docs/01_requirements/key_requirements.md — Functional + non-functional requirements in one place (GUI expectations, storage, formats, reliability, cross-platform).
- docs/01_requirements/system_acceptance_tests.md — Acceptance tests written as checkable items (used as “definition of done” for releases).

----------------------------------------------------------------------------------------------
Use cases (user actions + system responses)
- docs/02_use_cases/use_cases_u01_u19.md — U01–U19. Each use case should include: goal, preconditions, main flow, alternate flows, and result.
- docs/02_use_cases/use_case_diagram.md — The use case diagram and a short note explaining actors + boundaries.

----------------------------------------------------------------------------------------------
Features (what we are building, grouped as work items)
- docs/03_features/feature_list_f01_f09.md — F01–F09 with description, priority/effort/time, and acceptance criteria.
- docs/03_features/feature_to_usecase_traceability.md — Simple mapping of:
  - Feature → which use cases it supports
  - Feature → which acceptance tests prove it’s done
  (Helps avoid building “extra” stuff that isn’t required.)

----------------------------------------------------------------------------------------------
Technical design (how it works internally)
- docs/04_technical_design/architecture_overview.md — Module breakdown (GUI, controllers, data layer, integrations, exporters), plus the basic data flow from input → lookup → store → export.
- docs/04_technical_design/database_schema.md — SQLite tables/fields and what they mean. Include how records are updated and how “attempted/failed” items are tracked.
- docs/04_technical_design/core_data_logic_isbn_lccn_nlmcn.md — Identifier rules and parsing/validation logic (normalization, edge cases, what counts as invalid, what gets retried, etc.).
- docs/04_technical_design/http_api_integration.md — HTTP sources used, request/response handling, retry rules, timeouts, and how results are merged/prioritized.
- docs/04_technical_design/z3950_integration.md — How Z39.50 targets are queried, connection behavior, parsing strategy, and what happens when a target fails.
- docs/04_technical_design/io_and_exporting.md — Input file formats and validation rules, output files (TSVs, reports), expected columns, naming, and where files are saved.
- docs/04_technical_design/configuration_and_targets.md — Target list format, add/edit/remove rules, persistence, and any “defaults” the app uses.

----------------------------------------------------------------------------------------------
Delivery plan (how we deliver it)
- docs/05_delivery_plan/delivery_plan_iterations_1_to_6.md — Iteration 1–6 goals, what is delivered each iteration, and what marks completion.

----------------------------------------------------------------------------------------------
Dependency charts (work dependencies)
- docs/06_dependency_charts/legend_d0.md — Legend for dependency charts (what colors/arrows mean).
- docs/06_dependency_charts/dependency_charts_d1_to_d8.md — Dependency charts D1–D8 and short notes explaining the critical dependencies.

----------------------------------------------------------------------------------------------
Risk management (what can go wrong)
- docs/07_risk_management/rmmm_plan.md — Risks + mitigation + monitoring + what we do if the risk happens (integration risks, data quality, schedule, scope, etc.).

----------------------------------------------------------------------------------------------
Diagrams (process + interactions)
- docs/08_diagrams/activity_diagrams_a01_a19.md — A01–A19 with a short description for each activity diagram (what flow it represents).
- docs/08_diagrams/state_diagram.md — State diagram with brief explanations of states and transitions.
- docs/08_diagrams/sequence_diagrams_s01_s19.md — S01–S19 with a short description of each sequence (which components/services are involved and why).

----------------------------------------------------------------------------------------------
Dev guides (how we build/test/release it)
- docs/09_dev_guides/environment_setup.md — Setup steps (Python version, venv, install deps, run app). Keep it short but complete.
- docs/09_dev_guides/coding_standards.md — Naming conventions, restrictions (Python only), docstrings, and Git workflow rules.
- docs/09_dev_guides/testing_strategy.md — What to test and how (unit tests for parsing/validation, integration tests for APIs/Z39.50, basic GUI checks). Reference acceptance tests.
- docs/09_dev_guides/deployment_and_packaging.md — Packaging/build notes and what artifacts are produced for submission/handoff.

----------------------------------------------------------------------------------------------
User guides (how to run it)
- docs/10_user_guides/user_quickstart.md — Minimal “run a harvest” instructions: load input → configure targets → start → monitor → export.
- docs/10_user_guides/gui_guide.md — What each screen/tab does, and what each button/field affects.
- docs/10_user_guides/troubleshooting.md — Common problems + fixes (network errors, unreachable targets, bad input formatting, export issues).