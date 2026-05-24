# newdb — Database Project Generator

Generates a skeletal Python database project using SQLAlchemy 2.0+, Alembic,
and SQLite3, with a migration path to PostgreSQL.

## Usage

```bash
python generate.py <project_name> [--output-dir <path>]
```

Example:

```bash
python generate.py inventory
```

This creates an `inventory/` directory with a complete project skeleton.

## Generated Structure

```
<project>/
├── pyproject.toml
├── .gitignore
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── src/
│   └── <project>/
│       ├── __init__.py
│       ├── config.py
│       ├── database.py
│       ├── cli.py
│       └── models/
│           ├── __init__.py
│           └── base.py
├── tests/
│   ├── conftest.py
│   └── test_models.py
└── data/
```

## What You Get

- **SQLAlchemy 2.0 style** — `DeclarativeBase`, `Mapped`, `mapped_column`
- **TimestampMixin** — `created_at` and `updated_at` on all models
- **SQLite FK enforcement** — `PRAGMA foreign_keys=ON` via engine event listener
  (SQLite ignores FK constraints by default)
- **Alembic with `render_as_batch=True`** — required for SQLite schema migrations
  (SQLite doesn't support most ALTER TABLE operations natively)
- **Environment variable for DB URL** — `<PROJECT>_DATABASE_URL` overrides the
  default SQLite path (`~/.local/share/<project>/<project>.sqlite3`)
- **PostgreSQL optional dependency** — `pip install -e '.[postgres]'`
- **Click CLI** — skeletal command-line interface with `init-db`, `add`, `list`,
  `update`, `delete`, and `sql` subcommands ready to extend
- **Test scaffolding** — pytest with in-memory SQLite fixture

## Getting Started

After generating:

```bash
cd <project>
pip install -e '.[dev]'
```

### Add a model

Create `src/<project>/models/example.py`:

```python
from typing import Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Example(TimestampMixin, Base):
    __tablename__ = "example"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(500))
```

Then update `src/<project>/models/__init__.py`:

```python
from .base import Base, TimestampMixin
from .example import Example

__all__ = ["Base", "TimestampMixin", "Example"]
```

### Add CLI commands

The generated `cli.py` has skeletal `add`, `list`, `update`, and `delete`
command groups with commented-out examples. To add a command for the Example
model above:

```python
@add.command()
@click.argument("name")
@click.option("--description", "-d", help="Description")
def example(name, description):
    """Add an example resource."""
    from .models import Example
    with get_session() as session:
        obj = Example(name=name, description=description)
        session.add(obj)
        session.commit()
        click.echo(f"Added example: {name}")
```

The CLI entry point is registered in `pyproject.toml` as
`<project> = "<project>.cli:cli"`, so after `pip install -e .`:

```bash
<project> init-db           # Create tables
<project> add example foo   # Add a record
<project> list examples     # List records
<project> sql "SELECT ..."  # Ad-hoc queries
```

### Generate and apply the initial migration

```bash
alembic revision --autogenerate -m "initial"
alembic upgrade head
```

### Subsequent schema changes

1. Edit or add models
2. `alembic revision --autogenerate -m "description"`
3. Review the generated migration in `alembic/versions/`
4. `alembic upgrade head`

## Schema Change Workflow

To alter a table schema (e.g., add a column, change a field length):

1. Edit the model in `src/<project>/models/<table>.py`
2. Generate a migration: `alembic revision --autogenerate -m "description"`
3. Review the generated migration in `alembic/versions/`
4. Apply it: `alembic upgrade head`

Alembic diffs your models against the database and generates the migration
automatically. Always review before applying — autogenerate occasionally
gets renames or complex changes wrong.

### Non-disruptive changes (safe)

- Adding a nullable column
- Adding a column with a default value
- Adding a new table
- Adding an index
- Increasing a VARCHAR length
- Adding a nullable foreign key column

### Potentially disruptive changes

- Adding a NOT NULL column without a default — fails if rows exist
- Decreasing a VARCHAR length — may truncate data
- Removing or renaming a column — data loss or misdetection by Alembic
- Changing a column type — depends on data compatibility
- Adding a UNIQUE constraint — fails if duplicates exist

### SQLite caveat

SQLite doesn't support most `ALTER TABLE` operations natively (only add
column and rename table). The generated Alembic config uses
`render_as_batch=True`, which recreates the table behind the scenes
(create new → copy data → drop old → rename). This makes all operations
work, but is slower on large tables and temporarily doubles storage.

### Stamping an existing database

If the database was created with `Base.metadata.create_all()` rather than
through Alembic migrations, Alembic won't know the current schema state.
Before generating your first migration, stamp it:

```bash
alembic stamp head
```

This is a one-time fix — subsequent migrations will apply cleanly.

## PostgreSQL Migration

When ready to migrate from SQLite to PostgreSQL:

```bash
# Install the PostgreSQL driver
pip install -e '.[postgres]'

# Point at PostgreSQL
export <PROJECT>_DATABASE_URL=postgresql+psycopg2://user:pass@host/dbname

# Create the schema
alembic upgrade head

# Migrate data from SQLite (e.g., via pgloader or a custom script)
```

The models are dialect-agnostic. The only SQLite-specific code is the
`PRAGMA foreign_keys` listener in `database.py`, which is guarded by a
URL prefix check and harmlessly skipped for PostgreSQL.

## Running Tests

```bash
pytest tests/
```

Tests use an in-memory SQLite database — no on-disk state needed.

## Design Notes

- **Nullable FKs** are recommended for optional relationships so records
  can be added incrementally before all references are known
- **Named FK constraints** are required for Alembic batch mode on SQLite
  (use `batch_op.create_foreign_key('fk_table_column', ...)`)
- **`passive_deletes=True`** on relationships prevents SQLAlchemy from
  silently nullifying FK references before a delete — use this when you
  want the database to enforce referential integrity
- **Many-to-many relationships** use junction tables with CASCADE deletes
  on both foreign keys
