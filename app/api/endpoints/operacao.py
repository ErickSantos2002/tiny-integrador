"""Saúde da ingestão — para o DataCoreHS mostrar quando uma carga deu errado.

Sem isto, a falha de uma carga só existe no journal da VPS: alguém precisaria abrir SSH
e procurar. O resultado prático é que ninguém olha, e o erro aparece semanas depois como
número estranho num relatório.

A regra do que é "problema" NÃO está aqui: mora na view `operacao.avisos_cargas`
(migration 006). Este módulo só serve a view. É de propósito — se cada tela reimplementar
o critério, elas discordam entre si na primeira mudança de horário de timer.
"""

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.database import SessionLocal

router = APIRouter(prefix="/operacao", tags=["Operação"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class AvisoCarga(BaseModel):
    job: str
    rotulo: str
    estado: str            # ok | falha | inacabada | atrasada | sem_registro
    mensagem: str
    execucao_id: Optional[int] = None
    inicio: Optional[Any] = None
    fim: Optional[Any] = None
    resultado: Optional[str] = None
    erros: Optional[int] = None
    contagens: Optional[dict] = None
    horas_desde_inicio: Optional[float] = None


class Execucao(BaseModel):
    id: int
    job: str
    inicio: Any
    fim: Optional[Any] = None
    resultado: Optional[str] = None
    erros: int
    contagens: dict
    detalhe: Optional[str] = None
    argumentos: Optional[str] = None


@router.get("/avisos", response_model=List[AvisoCarga])
def avisos_das_cargas(
    apenas_problemas: bool = Query(True, description="false devolve também as cargas em dia"),
    db: Session = Depends(get_db),
):
    """Estado atual de cada carga da ingestão, com a mensagem pronta para exibir.

    O padrão é `apenas_problemas=true` porque a tela normal é a tela silenciosa: quando
    tudo está bem, o frontend recebe lista vazia e não mostra nada.
    """
    sql = "SELECT * FROM operacao.avisos_cargas"
    if apenas_problemas:
        sql += " WHERE estado <> 'ok'"
    sql += " ORDER BY CASE estado WHEN 'falha' THEN 1 WHEN 'atrasada' THEN 2 " \
           "WHEN 'sem_registro' THEN 3 WHEN 'inacabada' THEN 4 ELSE 5 END, job"
    linhas = db.execute(text(sql)).mappings().all()
    return [AvisoCarga(**dict(linha)) for linha in linhas]


@router.get("/execucoes", response_model=List[Execucao])
def historico_de_execucoes(
    job: Optional[str] = Query(None, description="filtra por job (extrair_notas, ...)"),
    limite: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Histórico bruto das cargas: quando rodou, quanto trouxe, quanto demorou.

    Serve para o gráfico de volume — "hoje chegaram 3 notas em vez de 300" é uma falha
    que nenhum código de saída detecta, porque o job termina feliz.
    """
    sql = "SELECT * FROM operacao.execucoes_job"
    params: dict = {"limite": limite}
    if job:
        sql += " WHERE job = :job"
        params["job"] = job
    sql += " ORDER BY inicio DESC LIMIT :limite"
    linhas = db.execute(text(sql), params).mappings().all()
    return [Execucao(**dict(linha)) for linha in linhas]
