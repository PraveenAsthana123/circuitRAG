import os
import psycopg2
from psycopg2.extras import RealDictCursor


class PostgresClient:
    def __init__(self):
        self.conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            dbname=os.getenv("POSTGRES_DB", "aios"),
            user=os.getenv("POSTGRES_USER", "aiuser"),
            password=os.getenv("POSTGRES_PASSWORD", "aipassword")
        )

    def query(self, sql: str, params: tuple = ()):
        with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(sql, params)
            self.conn.commit()

            if cursor.description:
                return cursor.fetchall()

            return []

    def close(self):
        self.conn.close()
