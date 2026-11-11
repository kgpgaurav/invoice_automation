"""Explicit PostgreSQL checkpoint setup; isolated from business-table migrations."""

import re
from contextlib import contextmanager

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from sqlalchemy import text

from app.ownership import owned_session


def checkpoint_schema(engine):
    with engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()")) + "_lg"
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", schema):
        raise ValueError("Invalid checkpoint schema")
    return schema


class FencedPostgresSaver(PostgresSaver):
    def __init__(self, connection, worker, claim):
        super().__init__(connection)
        self.worker, self.claim = worker, claim

    def put(self, *args, **kwargs):
        with owned_session(self.worker, self.claim):
            return super().put(*args, **kwargs)

    def put_writes(self, *args, **kwargs):
        with owned_session(self.worker, self.claim):
            return super().put_writes(*args, **kwargs)


@contextmanager
def checkpoint_store(engine, worker=None, claim=None):
    schema = checkpoint_schema(engine)
    kwargs = engine.url.translate_connect_args(username="user", database="dbname")
    kwargs.update(engine.url.query)
    kwargs.update(options=f"-c search_path={schema} -c statement_timeout=10000")
    with psycopg.connect(
        **kwargs, autocommit=True, prepare_threshold=0, connect_timeout=5, row_factory=dict_row
    ) as connection:
        yield (
            FencedPostgresSaver(connection, worker, claim) if worker else PostgresSaver(connection)
        )


def setup_checkpoints(engine):
    schema = checkpoint_schema(engine)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    with checkpoint_store(engine) as saver:
        saver.setup()
