#!/usr/bin/env python3

"""
Generate a new SQLAlchemy 2.0 + Alembic + SQLite3 database project.

Creates a complete project skeleton with:
- src layout Python package
- SQLAlchemy 2.0 models with DeclarativeBase and TimestampMixin
- Alembic configured with render_as_batch for SQLite compatibility
- SQLite FK enforcement via engine event listener
- PostgreSQL migration path via environment variable
- pyproject.toml with dependencies

Usage:
    python generate.py <project_name> [--output-dir <path>]
"""

import argparse
import os
import sys
from pathlib import Path
from textwrap import dedent


def to_env_var(name: str) -> str:
    return name.upper().replace("-", "_")


def generate_project(name: str, output_dir: Path):
    project_dir = output_dir / name

    if project_dir.exists():
        print(f"Error: {project_dir} already exists", file=sys.stderr)
        raise SystemExit(1)

    pkg_name = name.replace("-", "_")
    env_var = f"{to_env_var(name)}_DATABASE_URL"

    # Directory structure
    dirs = [
        project_dir,
        project_dir / "alembic" / "versions",
        project_dir / "src" / pkg_name / "models",
        project_dir / "tests",
        project_dir / "data",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # --- pyproject.toml ---
    write(project_dir / "pyproject.toml", dedent(f"""\
        [project]
        name = "{name}"
        version = "0.1.0"
        description = ""
        requires-python = ">=3.9"
        dependencies = [
            "sqlalchemy>=2.0",
            "alembic>=1.13",
        ]

        [project.optional-dependencies]
        postgres = ["psycopg2-binary>=2.9"]
        dev = [
            "pytest>=7.0",
            "pytest-cov",
            "ruff",
        ]

        [build-system]
        requires = ["setuptools>=68.0"]
        build-backend = "setuptools.build_meta"

        [tool.setuptools.packages.find]
        where = ["src"]

        [tool.ruff]
        target-version = "py39"
        line-length = 100
    """))

    # --- src/<pkg>/__init__.py ---
    write(project_dir / "src" / pkg_name / "__init__.py", "")

    # --- src/<pkg>/config.py ---
    write(project_dir / "src" / pkg_name / "config.py", dedent(f"""\
        import os
        from pathlib import Path

        _DEFAULT_DB_DIR = Path.home() / ".local" / "share" / "{name}"
        _DEFAULT_DB_PATH = _DEFAULT_DB_DIR / "{name}.sqlite3"

        DATABASE_URL = os.environ.get(
            "{env_var}",
            f"sqlite:///{{_DEFAULT_DB_PATH}}",
        )
    """))

    # --- src/<pkg>/database.py ---
    write(project_dir / "src" / pkg_name / "database.py", dedent(f"""\
        from typing import Optional

        from sqlalchemy import create_engine, event
        from sqlalchemy.orm import Session, sessionmaker

        from .config import DATABASE_URL, _DEFAULT_DB_DIR


        def _create_engine(url: Optional[str] = None):
            db_url = url or DATABASE_URL
            if db_url.startswith("sqlite") and ":memory:" not in db_url:
                _DEFAULT_DB_DIR.mkdir(parents=True, exist_ok=True)
            connect_args = {{}}
            if db_url.startswith("sqlite"):
                connect_args["check_same_thread"] = False
            eng = create_engine(db_url, connect_args=connect_args, echo=False)
            if db_url.startswith("sqlite"):

                @event.listens_for(eng, "connect")
                def _set_sqlite_pragma(dbapi_connection, connection_record):
                    cursor = dbapi_connection.cursor()
                    cursor.execute("PRAGMA foreign_keys=ON")
                    cursor.close()

            return eng


        engine = _create_engine()
        SessionLocal = sessionmaker(bind=engine)


        def get_session() -> Session:
            return SessionLocal()
    """))

    # --- src/<pkg>/models/__init__.py ---
    write(project_dir / "src" / pkg_name / "models" / "__init__.py", dedent("""\
        \"\"\"All models imported here for Alembic autogenerate to detect them.\"\"\"

        from .base import Base, TimestampMixin

        __all__ = [
            "Base",
            "TimestampMixin",
        ]
    """))

    # --- src/<pkg>/models/base.py ---
    write(project_dir / "src" / pkg_name / "models" / "base.py", dedent("""\
        from datetime import datetime

        from sqlalchemy import func
        from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


        class Base(DeclarativeBase):
            pass


        class TimestampMixin:
            created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
            updated_at: Mapped[datetime] = mapped_column(
                server_default=func.now(), onupdate=func.now(), nullable=False
            )
    """))

    # --- alembic.ini ---
    write(project_dir / "alembic.ini", dedent(f"""\
        [alembic]
        script_location = alembic
        prepend_sys_path = .
        sqlalchemy.url = sqlite:///data/{name}.sqlite3

        [loggers]
        keys = root,sqlalchemy,alembic

        [handlers]
        keys = console

        [formatters]
        keys = generic

        [logger_root]
        level = WARN
        handlers = console

        [logger_sqlalchemy]
        level = WARN
        handlers =
        qualname = sqlalchemy.engine

        [logger_alembic]
        level = INFO
        handlers =
        qualname = alembic

        [handler_console]
        class = StreamHandler
        args = (sys.stderr,)
        level = NOTSET
        formatter = generic

        [formatter_generic]
        format = %(%(levelname)-5.5s [%(name)s] %(message)s
        datefmt = %H:%M:%S
    """))

    # --- alembic/env.py ---
    write(project_dir / "alembic" / "env.py", dedent(f"""\
        from logging.config import fileConfig

        from alembic import context
        from sqlalchemy import engine_from_config, pool

        from {pkg_name}.config import DATABASE_URL
        from {pkg_name}.models import Base

        config = context.config
        config.set_main_option("sqlalchemy.url", DATABASE_URL)

        if config.config_file_name is not None:
            fileConfig(config.config_file_name)

        target_metadata = Base.metadata


        def run_migrations_offline() -> None:
            url = config.get_main_option("sqlalchemy.url")
            context.configure(
                url=url,
                target_metadata=target_metadata,
                literal_binds=True,
                dialect_opts={{"paramstyle": "named"}},
                render_as_batch=True,
            )
            with context.begin_transaction():
                context.run_migrations()


        def run_migrations_online() -> None:
            connectable = engine_from_config(
                config.get_section(config.config_ini_section, {{}}),
                prefix="sqlalchemy.",
                poolclass=pool.NullPool,
            )
            with connectable.connect() as connection:
                context.configure(
                    connection=connection,
                    target_metadata=target_metadata,
                    render_as_batch=True,
                )
                with context.begin_transaction():
                    context.run_migrations()


        if context.is_offline_mode():
            run_migrations_offline()
        else:
            run_migrations_online()
    """))

    # --- alembic/script.py.mako ---
    write(project_dir / "alembic" / "script.py.mako", dedent("""\
        \"\"\"${message}

        Revision ID: ${up_revision}
        Revises: ${down_revision | comma,n}
        Create Date: ${create_date}

        \"\"\"
        from typing import Sequence, Union

        from alembic import op
        import sqlalchemy as sa
        ${imports if imports else ""}

        # revision identifiers, used by Alembic.
        revision: str = ${repr(up_revision)}
        down_revision: Union[str, None] = ${repr(down_revision)}
        branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
        depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


        def upgrade() -> None:
            ${upgrades if upgrades else "pass"}


        def downgrade() -> None:
            ${downgrades if downgrades else "pass"}
    """))

    # --- tests/conftest.py ---
    write(project_dir / "tests" / "conftest.py", dedent(f"""\
        import pytest
        from sqlalchemy import create_engine, event
        from sqlalchemy.orm import sessionmaker

        from {pkg_name}.models import Base


        @pytest.fixture
        def db_session():
            engine = create_engine("sqlite:///:memory:")

            @event.listens_for(engine, "connect")
            def _set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

            Base.metadata.create_all(engine)
            session_factory = sessionmaker(bind=engine)
            session = session_factory()
            yield session
            session.close()
    """))

    # --- tests/test_models.py ---
    write(project_dir / "tests" / "test_models.py", dedent(f"""\
        from {pkg_name}.models import Base


        def test_base_metadata(db_session):
            \"\"\"Verify that the database schema creates without errors.\"\"\"
            assert Base.metadata.tables is not None
    """))

    # --- .gitignore ---
    write(project_dir / ".gitignore", dedent("""\
        __pycache__/
        *.py[cod]
        *.egg-info/
        dist/
        build/
        *.sqlite3
        .env
    """))

    print(f"Created project: {project_dir}")
    print()
    print("Next steps:")
    print(f"  cd {project_dir}")
    print(f"  pip install -e '.[dev]'")
    print(f"  # Add models to src/{pkg_name}/models/")
    print(f"  # Update src/{pkg_name}/models/__init__.py with imports")
    print(f"  alembic revision --autogenerate -m 'initial'")
    print(f"  alembic upgrade head")
    print()
    print("PostgreSQL migration:")
    print(f"  export {env_var}=postgresql+psycopg2://user:pass@host/{name}")
    print(f"  pip install -e '.[postgres]'")
    print(f"  alembic upgrade head")


def write(path: Path, content: str):
    path.write_text(content)


def main():
    parser = argparse.ArgumentParser(
        description="Generate a new SQLAlchemy/Alembic/SQLite3 database project"
    )
    parser.add_argument(
        "name",
        help="Project name (used for package, directory, env var, and DB filename)",
    )
    parser.add_argument(
        "--output-dir", "-o", type=Path, default=Path.cwd(),
        help="Parent directory to create the project in (default: current directory)",
    )
    args = parser.parse_args()

    if not args.name.replace("-", "_").isidentifier():
        print(f"Error: '{args.name}' is not a valid Python package name", file=sys.stderr)
        raise SystemExit(1)

    generate_project(args.name, args.output_dir)


if __name__ == "__main__":
    main()
