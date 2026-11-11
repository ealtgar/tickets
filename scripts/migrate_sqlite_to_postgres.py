#!/usr/bin/env python3
"""Copia los datos de la base SQLite (tickets.db) a PostgreSQL.

Requisitos:
    1. El esquema de PostgreSQL ya debe existir: ``alembic upgrade head``.
    2. La base de destino debe estar vacía o usar ``--force`` (vacía las tablas).

Ejemplos:
    python scripts/migrate_sqlite_to_postgres.py
    python scripts/migrate_sqlite_to_postgres.py --sqlite-path tickets.db --force
    DATABASE_URL=postgresql+psycopg://... python scripts/migrate_sqlite_to_postgres.py

El script conserva los IDs originales y reajusta las secuencias de PostgreSQL
para que los nuevos registros no choquen con los ya copiados.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import models  # noqa: E402
from app.database import DATABASE_URL, normalize_database_url  # noqa: E402

# Orden respetando las claves foráneas.
MODELS = [
    models.User,
    models.Ticket,
    models.Comment,
    models.RefreshToken,
    models.OAuthAccount,
]


def _fetch_rows(session, model) -> list[dict]:
    rows: list[dict] = []
    for obj in session.scalars(select(model).order_by(model.id)):
        row = {}
        for column in model.__table__.columns:
            value = getattr(obj, column.key)
            # SQLite devuelve datetimes sin zona horaria; los datos originales
            # se guardaron en UTC.
            if isinstance(value, datetime) and value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            row[column.key] = value
        rows.append(row)
    return rows


def _reset_sequences(session) -> None:
    for model in MODELS:
        table = model.__tablename__
        session.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1), "
                f"(SELECT MAX(id) IS NOT NULL FROM {table}))"
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migra los datos de SQLite a PostgreSQL."
    )
    parser.add_argument(
        "--sqlite-path",
        default=str(ROOT / "tickets.db"),
        help="Ruta al archivo SQLite de origen (por defecto: tickets.db).",
    )
    parser.add_argument(
        "--database-url",
        default=DATABASE_URL,
        help="URL de PostgreSQL de destino (por defecto: DATABASE_URL).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Vacía las tablas de destino antes de copiar los datos.",
    )
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite_path)
    if not sqlite_path.is_file():
        print(f"ERROR: no existe el archivo SQLite: {sqlite_path}", file=sys.stderr)
        return 1

    database_url = normalize_database_url(args.database_url)
    if not database_url.startswith("postgresql"):
        print(
            "ERROR: --database-url debe ser una URL de PostgreSQL "
            "(postgresql://... o postgresql+psycopg://...).",
            file=sys.stderr,
        )
        return 1

    source_engine = create_engine(f"sqlite:///{sqlite_path}")
    target_engine = create_engine(database_url, pool_pre_ping=True)

    existing_tables = set(inspect(target_engine).get_table_names())
    missing = [model.__tablename__ for model in MODELS if model.__tablename__ not in existing_tables]
    if missing:
        print(
            "ERROR: faltan tablas en PostgreSQL: "
            + ", ".join(missing)
            + "\nEjecuta primero: alembic upgrade head",
            file=sys.stderr,
        )
        return 1

    SourceSession = sessionmaker(bind=source_engine)
    TargetSession = sessionmaker(bind=target_engine)

    try:
        with TargetSession() as target:
            existing = sum(
                target.scalar(select(func.count()).select_from(model)) or 0
                for model in MODELS
            )
            if existing and not args.force:
                print(
                    "ERROR: la base de destino ya contiene datos "
                    f"({existing} filas). Usa --force para reemplazarlos.",
                    file=sys.stderr,
                )
                return 1

            if args.force:
                tables = ", ".join(model.__tablename__ for model in MODELS)
                target.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
                target.commit()

            with SourceSession() as source:
                for model in MODELS:
                    rows = _fetch_rows(source, model)
                    if rows:
                        target.bulk_insert_mappings(model, rows)
                    target.commit()
                    print(f"{model.__tablename__}: {len(rows)} filas copiadas")

            _reset_sequences(target)
            target.commit()
    finally:
        source_engine.dispose()
        target_engine.dispose()

    print("Migración completada correctamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
