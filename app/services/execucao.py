"""Registro de execução das cargas, em `operacao.execucoes_job`.

Existe porque o código de saída dos jobs não chega a ninguém: ele morre no journal da
VPS. Gravando no banco, a máquina do Erick consegue ler o estado sem SSH (a chave dele
tem passphrase, e o JARVIS dispara antes do ssh-agent ter identidade) — ver migration 005.

Duas decisões que fazem este arquivo parecer mais complicado do que seria:

1. **Sessão própria, separada da sessão dos dados.** Se o job der rollback no meio de um
   registro, o registro da execução não pode ir junto — ele existe justamente para contar
   que algo deu errado. Compartilhar a sessão faria o alarme sumir exatamente na hora em
   que ele importa.

2. **Falha aqui nunca derruba a carga.** Um problema ao gravar o log de execução não pode
   impedir 8 mil notas de entrar. Toda falha própria é registrada e engolida — o job
   continua, e o pior caso é ficar sem o registro daquela passagem.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from sqlalchemy import BigInteger, Column, DateTime, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB

from app.models.database import Base, SessionLocal

logger = logging.getLogger(__name__)


class ExecucaoJob(Base):
    __tablename__ = "execucoes_job"
    __table_args__ = {"schema": "operacao"}

    id = Column(BigInteger, primary_key=True)
    job = Column(Text, nullable=False)
    inicio = Column(DateTime(timezone=True), nullable=False)
    fim = Column(DateTime(timezone=True), nullable=True)
    # NULL = o job não chegou ao fim (morto por deploy, VPS caiu). Diferente de "falha".
    resultado = Column(Text, nullable=True)
    erros = Column(Integer, nullable=False, default=0)
    contagens = Column(JSONB, nullable=False, default=dict)
    detalhe = Column(Text, nullable=True)
    argumentos = Column(Text, nullable=True)


class Registro:
    """O que o job preenche enquanto roda. Só isto é público."""

    def __init__(self) -> None:
        self.contagens: dict[str, Any] = {}
        self.erros = 0
        self.detalhe: Optional[str] = None
        # None = decide por `erros`. O job sobrescreve com o próprio código de saída,
        # porque nem todo erro reprova a carga: `extrair_notas` e `extrair_estoque` saem
        # 0 quando erraram em alguns registros mas trouxeram o resto. O registro tem que
        # dizer a mesma coisa que o systemd viu, senão o alarme e o journal se contradizem.
        self.falhou: Optional[bool] = None


@contextmanager
def registrar_execucao(job: str, argumentos: str = "") -> Iterator[Registro]:
    """Abre uma linha em `operacao.execucoes_job` e a fecha ao sair.

    O `resultado` sai de `registro.erros` e de ter havido exceção — não do que o job
    imprime. Sair por exceção marca `falha` e re-levanta: quem decide o código de saída
    continua sendo o job.
    """
    registro = Registro()
    sessao = None
    linha_id = None

    try:
        sessao = SessionLocal()
        linha = ExecucaoJob(job=job, inicio=datetime.now(timezone.utc),
                            argumentos=argumentos or None)
        sessao.add(linha)
        sessao.commit()
        linha_id = linha.id
    except Exception as erro:                                  # noqa: BLE001
        logger.warning("não consegui abrir o registro de execução: %s", erro)
        if sessao is not None:
            sessao.rollback()

    try:
        yield registro
    except BaseException as erro:                              # noqa: BLE001
        # BaseException e não Exception: um job morto por Ctrl+C ou SystemExit também
        # merece ficar registrado como interrompido em vez de sumir.
        _fechar(sessao, linha_id, registro, "falha",
                registro.detalhe or f"{type(erro).__name__}: {erro}")
        raise
    else:
        falhou = registro.falhou if registro.falhou is not None else bool(registro.erros)
        _fechar(sessao, linha_id, registro, "falha" if falhou else "sucesso",
                registro.detalhe)
    finally:
        if sessao is not None:
            sessao.close()


def _fechar(sessao, linha_id, registro: Registro, resultado: str,
            detalhe: Optional[str]) -> None:
    if sessao is None or linha_id is None:
        return
    try:
        # Defensivo, e assumidamente NÃO coberto por teste: a sessão daqui é privada, então
        # nenhum caminho do contrato público consegue sujá-la. Protege do que sobra —
        # conexão devolvida quebrada pelo pool. Uma mutação removendo esta linha passa nos
        # testes; ela fica por barata, não por provada.
        sessao.rollback()
        sessao.execute(
            text("UPDATE operacao.execucoes_job SET fim = :fim, resultado = :resultado, "
                 "erros = :erros, contagens = CAST(:contagens AS jsonb), detalhe = :detalhe "
                 "WHERE id = :id"),
            {"fim": datetime.now(timezone.utc), "resultado": resultado,
             "erros": registro.erros, "contagens": _json(registro.contagens),
             "detalhe": detalhe, "id": linha_id})
        sessao.commit()
    except Exception as erro:                                  # noqa: BLE001
        logger.warning("não consegui fechar o registro de execução: %s", erro)
        try:
            sessao.rollback()
        except Exception:                                      # noqa: BLE001
            pass


def _json(contagens: dict) -> str:
    import json
    # as contagens vêm de `dict[str, int]`, mas um `default=str` evita que um valor
    # inesperado (um Decimal, uma data) derrube a gravação do registro inteiro
    return json.dumps(contagens, default=str, ensure_ascii=False)
