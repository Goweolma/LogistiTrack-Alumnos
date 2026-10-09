"""Conexión común a PostgreSQL."""

import os

import psycopg


def get_connection():
    """Abre una conexión nueva usando DATABASE_URL, sin pool compartido.

    El llamador administra su cierre y la transacción; los servicios utilizan
    ``with get_connection()`` para confirmar al salir o revertir ante errores.
    Lanza RuntimeError si falta la variable y propaga los errores de psycopg.
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL no está configurada")
    return psycopg.connect(database_url)

