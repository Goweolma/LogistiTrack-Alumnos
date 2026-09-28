"""Conexión común a PostgreSQL."""

import os

import psycopg


def get_connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL no está configurada")
    return psycopg.connect(database_url)

