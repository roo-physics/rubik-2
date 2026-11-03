import uuid

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


def new_id() -> str:
    """PK de todas as tabelas: uuid4 canônico (36 chars com traços)."""
    return str(uuid.uuid4())


class Cadastro(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True, max_length=36)
    nome: str | None = None
    email: str | None = None
    hashed_password: str | None = None
    role: str | None = 'usuario_externo'
    disabled: bool | None = False

    inscricoes: list["Inscricao"] = Relationship(back_populates="cadastro")


class Campeonato(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True, max_length=36)
    modalidade: str | None = None
    sobre_o_campeonato: str | None = None
    local: str | None = None
    data: str | None = None
    inscricoes_abertura: str | None = None
    inscricoes_fim: str | None = None

    rodadas: list["Rodada"] = Relationship(back_populates="campeonato")
    inscricoes: list["Inscricao"] = Relationship(back_populates="campeonato")


class Inscricao(SQLModel, table=True):
    __table_args__ = (UniqueConstraint('campeonato_id', 'cadastro_id'),)

    id: str = Field(default_factory=new_id, primary_key=True, max_length=36)

    campeonato_id: str = Field(foreign_key="campeonato.id", max_length=36)
    cadastro_id: str = Field(foreign_key="cadastro.id", max_length=36)

    campeonato: Campeonato = Relationship(back_populates="inscricoes")
    cadastro: Cadastro = Relationship(back_populates="inscricoes")
    tentativas: list["Tentativa"] = Relationship(back_populates="inscricao")


class Rodada(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True, max_length=36)
    formato: str | None = None
    posicao_rodada: int | None = None
    tempo_maximo: str | None = None
    percent_aprovados: int | None = None
    maximo_grupo: int | None = None
    n_pessoas_aprovadas: int | None = None
    travada: bool | None = False

    campeonato_id: str | None = Field(default=None, foreign_key="campeonato.id",
                                      max_length=36)

    campeonato: Campeonato | None = Relationship(back_populates="rodadas")
    tentativas: list["Tentativa"] = Relationship(back_populates="rodada")


class Tentativa(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True, max_length=36)
    situacao: str | None = None
    numero: int
    horario_inicio: int | None = None
    duracao: int | None = None
    grupo: int | None = None

    rodada_id: str | None = Field(default=None, foreign_key="rodada.id", max_length=36)
    inscricao_id: str | None = Field(default=None, foreign_key="inscricao.id",
                                     max_length=36)

    rodada: Rodada | None = Relationship(back_populates="tentativas")
    inscricao: Inscricao | None = Relationship(back_populates="tentativas")
