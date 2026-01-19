# Contribution & Branch Workflow

This document describes how our team works on the LCCN Harvester codebase:
how branches are created, how changes are committed, and how work in the
sprint log maps to Git activity.

The goals are:
- Keep `main` stable and always releasable.
- Make it easy to see which code changes belong to which sprint task.
- Reduce merge conflicts and accidental overwrites.
- Support the roles of Team Lead, Tech Lead, Version Manager, and Lead Tester.

---

## 1. Branches

We use three types of branches:

- `main`  
  - Always stable and releasable.  
  - Only the Version Manager (or someone they delegate) merges into `main`.  
  - Each completed sprint is tagged on `main` (e.g., `sprint-1`, `sprint-2`).

- `develop`  
  - Main integration branch.  
  - Feature branches are created from `develop` and merged back into `develop` when completed.  
  - `develop` should always build and pass the automated test suite.

- `feature/*`  
  - One feature branch per sprint task.  
  - Branch name format:  
    `feature/<sprint>-<task-id>-short-name`  
    Examples:  
    - `feature/S1-T01-contribution-workflow`  
    - `feature/S1-T10-init-db`  
  - Created from `develop`, deleted after merge.

---

## 2. Mapping Sprint Tasks to Branches

- Every task in the Sprint Log has an ID (e.g., `S1-T03`).  
- When starting a task:
  1. Create a feature branch from `develop` using the naming pattern above.
  2. Track all work time for that task under the same ID in your personal time log.

- A task is considered **Done** when:
  - The code for the task is implemented on its feature branch.
  - Relevant tests have been added/updated and recorded in the testing log.
  - Any related documentation (if needed) has been updated.
  - The branch has been merged back into `develop`.

---

## 3. Commit Messages

Commit messages must be:

- Short and meaningful.
- Prefixed with the sprint-task ID.

Format:

`S1-T03: short description of change`

Examples:

- `S1-T03: add docs/contribution_workflow.md`
- `S1-T10: implement init_db and create main/attempted tables`

This makes it easy to trace commits back to sprint tasks and hours.

---

## 4. Workflow for Making a Change

1. **Sync and branch**
   - Pull the latest `develop`:
     - `git checkout develop`
     - `git pull`
   - Create a feature branch:
     - `git checkout -b feature/S1-T03-contribution-workflow`

2. **Implement the task**
   - Make code/doc changes related to this task only.
   - Run tests that are relevant to your changes.

3. **Commit changes**
   - Stage and commit with a proper message:
     - `git add ...`
     - `git commit -m "S1-T03: describe contrib & branch workflow"`

4. **Update testing log**
   - For any tests you ran (unit, integration, manual), add an entry to the testing log
     with date, component, test type, and result.

5. **Push branch**
   - `git push -u origin feature/S1-T03-contribution-workflow`

6. **Merge into `develop`**
   - Open a Pull Request (PR) from your feature branch into `develop`.
   - At least one teammate reviews and checks that:
     - Code builds / tests pass.
     - Testing log entries were added.
   - Version Manager (or delegate) merges the PR into `develop`.

7. **Sync and clean up**
   - After merge:
     - `git checkout develop`
     - `git pull`
   - Delete the feature branch locally and on origin when no longer needed.

---

## 5. Merging into `main` and Tags

- At the end of a sprint, when the team agrees that `develop` is stable:
  - Version Manager fast-forwards or merges `develop` into `main`.
  - A tag is created on `main` for that sprint:
    - `sprint-1`, `sprint-2`, etc.

This ensures there is a clear, tagged snapshot of the code that corresponds
to each sprint review and to each version of the project plan.

---

## 6. Handling Hotfixes

If a critical bug is found in `main`:

1. Create a `hotfix/*` branch from `main`:
   - `git checkout main`
   - `git pull`
   - `git checkout -b hotfix/<short-description>`

2. Fix the bug, add tests, commit with a clear message.

3. Merge the hotfix into both `main` and `develop` via PRs.

Hotfixes should be rare; most work goes through the normal feature-branch workflow.
