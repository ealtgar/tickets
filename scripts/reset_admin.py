#!/usr/bin/env python3
"""Borra todos los usuarios de una base PostgreSQL (Render) y crea un admin.

Uso:
    python reset_admin_render.py --database-url "postgresql://..." \
        --tickets null

Opciones de --tickets:
    null    -> conserva los tickets y les quita el propietario (owner_id = NULL)
    delete  -> borra también tickets y comentarios
    keep    -> aborta si hay tickets que dependan de algún usuario
"""

from __future__ import annotations

import argparse
import secrets
import string
import sys
from urllib.parse import urlsplit, urlunsplit

import bcrypt
import psycopg


def normalize_url(url: str) -> str:
    # SQLAlchemy usa postgresql+psycopg://; psycopg quiere postgresql://
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def ensure_ssl(url: str) -> str:
    parts = urlsplit(url)
    query = parts.query
    if "sslmode=" not in query:
        query = f"{query}&sslmode=require" if query else "sslmode=require"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True,
                        help="External Database URL de Render")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--email", default="admin@example.com")
    parser.add_argument("--password", default=None,
                        help="Si se omite, se genera una aleatoria")
    parser.add_argument("--tickets", choices=("null", "delete", "keep"),
                        default="null")
    args = parser.parse_args()

    generated = args.password is None
    password = args.password or "".join(
        secrets.choice(string.ascii_letters + string.digits + "_-")
        for _ in range(20)
    )
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()

    url = ensure_ssl(normalize_url(args.database_url))
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM tickets t JOIN users u ON u.id = t.owner_id"
        )
        owned_tickets = cur.fetchone()[0]
        if args.tickets == "keep" and owned_tickets:
            print(
                f"ERROR: hay {owned_tickets} tickets con propietario. "
                "Usa --tickets null o --tickets delete.",
                file=sys.stderr,
            )
            return 1

        cur.execute("SELECT COUNT(*) FROM users")
        before = cur.fetchone()[0]

        if args.tickets == "delete":
            cur.execute("DELETE FROM comments")
            cur.execute("DELETE FROM tickets")
        else:
            cur.execute("UPDATE tickets SET owner_id = NULL")

        cur.execute("DELETE FROM refresh_tokens")
        cur.execute("DELETE FROM oauth_accounts")
        cur.execute("DELETE FROM users")

        cur.execute(
            """
            INSERT INTO users
                (username, email, hashed_password, is_active, is_superuser, role)
            VALUES (%s, %s, %s, TRUE, TRUE, 'admin'::userrole)
            """,
            (args.username, args.email, hashed),
        )
        conn.commit()

        cur.execute(
            "SELECT id, username, email, role, is_active, is_superuser FROM users"
        )
        rows = cur.fetchall()

    print(f"Usuarios eliminados: {before}")
    print("Usuarios restantes:")
    for row in rows:
        print(" ", row)
    print(f"\nUSUARIO: {args.username}")
    print(f"EMAIL:   {args.email}")
    if generated:
        print(f"PASSWORD: {password}")
    else:
        print("PASSWORD: (la indicada con --password)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
