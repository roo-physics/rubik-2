import os
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

import models  # noqa: F401  registers table classes on the metadata

# DB_PATH: em produção (Docker/App Platform) aponta para o volume (/data);
# sem a env, comportamento antigo — database.db ao lado do código.
DB_PATH = Path(os.getenv("DB_PATH") or Path(__file__).resolve().parent / "database.db")

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def init_db():
    SQLModel.metadata.create_all(engine)
    # Banco antigo: mudanças de schema não surgem pelo create_all (ele pula
    # tabelas existentes); aplica as migrações por SQL, idempotentes.
    with engine.connect() as conn:
        _migra_uuids(conn)
        cols = [r[1] for r in conn.exec_driver_sql('PRAGMA table_info(rodada)')]
        if 'travada' not in cols:
            conn.exec_driver_sql('ALTER TABLE rodada ADD COLUMN travada BOOLEAN')
        cols_cam = [r[1] for r in conn.exec_driver_sql('PRAGMA table_info(campeonato)')]
        for nova in ('inscricoes_abertura', 'inscricoes_fim'):
            if nova not in cols_cam:
                conn.exec_driver_sql(f'ALTER TABLE campeonato ADD COLUMN {nova} TEXT')
        conn.exec_driver_sql(
            'CREATE UNIQUE INDEX IF NOT EXISTS ux_inscricao_campeonato_cadastro '
            'ON inscricao (campeonato_id, cadastro_id)')
        conn.commit()


def get_session() -> Session:
    return Session(engine)


# ---------------- migração: PKs/FKs inteiras -> uuid4 em TEXT -------------

# tabelas referenciadas primeiro (os maps delas precisam existir nas FKs)
_MIG_ORDEM = ('campeonato', 'cadastro', 'rodada', 'inscricao', 'tentativa')

# uuid4 canônico gerado no próprio SQLite
_UUID_SQL = ("lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || "
             "'-4' || substr(lower(hex(randomblob(2))), 2) || "
             "'-a' || substr(lower(hex(randomblob(2))), 2) || "
             "'-' || lower(hex(randomblob(6)))")


def _id_eh_inteiro(conn, tabela):
    return any(r[1] == 'id' and r[2].upper() == 'INTEGER'
               for r in conn.exec_driver_sql(f'PRAGMA table_info({tabela})'))


def _migra_uuids(conn):
    """Reconstrói cada tabela com id TEXT (uuid4 novo por linha) e remapeia as
    FKs pelos maps temporários. Idempotente; é um commit só (no init_db) —
    se falhar no meio, nada é gravado."""
    if not any(_id_eh_inteiro(conn, t) for t in _MIG_ORDEM):
        return
    for tabela in _MIG_ORDEM:
        if not _id_eh_inteiro(conn, tabela):
            continue
        sql_origem = conn.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (tabela,)).fetchone()[0]
        sql_nova = sql_origem.replace('id INTEGER NOT NULL', 'id TEXT NOT NULL', 1) \
                              .replace('CREATE TABLE ' + tabela,
                                       'CREATE TABLE mig_' + tabela, 1)
        colunas = [r[1] for r in conn.exec_driver_sql(f'PRAGMA table_info({tabela})')
                   if r[1] != 'id']
        fks = {c: c[:-3] for c in colunas if c.endswith('_id')}  # 'rodada_id' -> 'rodada'
        conn.exec_driver_sql(f'CREATE TEMP TABLE map_{tabela} '
                             '(old_id INTEGER, new_id TEXT)')
        conn.exec_driver_sql(f'INSERT INTO map_{tabela} '
                             f'SELECT id, {_UUID_SQL} FROM {tabela}')
        proj = ', '.join(f'map_{fks[c]}.new_id' if c in fks else f'{tabela}.{c}'
                         for c in colunas)
        joins = f'LEFT JOIN map_{tabela} ON map_{tabela}.old_id = {tabela}.id ' + \
                ' '.join(f'LEFT JOIN map_{ref} ON map_{ref}.old_id = {tabela}.{c}'
                         for c, ref in fks.items())
        conn.exec_driver_sql(sql_nova)
        conn.exec_driver_sql(f'INSERT INTO mig_{tabela} '
                             f'SELECT map_{tabela}.new_id, {proj} '
                             f'FROM {tabela} {joins}')
        conn.exec_driver_sql(f'DROP TABLE {tabela}')
        conn.exec_driver_sql(f'ALTER TABLE mig_{tabela} RENAME TO {tabela}')
    for tabela in _MIG_ORDEM:
        conn.exec_driver_sql(f'DROP TABLE IF EXISTS main.map_{tabela}')
        conn.exec_driver_sql(f'DROP TABLE IF EXISTS map_{tabela}')
