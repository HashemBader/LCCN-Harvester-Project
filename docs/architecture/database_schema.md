# Database Schema (SQLite)

See [database_architecture.md](database_architecture.md) for the complete schema definition, including:

- `main` table — successful results (export-ready)
- `attempted` table — failed attempts (retry support)
- `linked_isbns` table — (stretch) edition linking
- `subjects` table — (stretch) subject phrases

The schema source file is `schema.sql` in the project root.