"""Gravação das NFS-e vindas do ADN em `tiny.servicos`.

Uma função só, usada pelos dois caminhos de entrada:

  * `POST /notas_servico/importar` — o disparo manual, que já existia;
  * `python -m app.jobs.importar_nfse` — o timer diário (desde 2026-09-11).

Até então a gravação morava dentro do endpoint. O job teria que copiá-la, e duas cópias
da regra de identidade da nota é exatamente como a régua de faturamento chegou a ter três
versões que divergiam em silêncio. A regra mora aqui; os dois caminhos só a chamam.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Iterable, List

from sqlalchemy.orm import Session

from app.models.nota_servico import NotaServico as NotaServicoModel

logger = logging.getLogger(__name__)

# Campos que são curadoria NOSSA, não dado da origem: a importação nunca os
# sobrescreve numa atualização. Hoje só `cancelada`, que é marcada à mão porque o
# leiaute nacional entrega o cancelamento como Evento separado, ainda não tratado.
# Sem esta proteção, cada reimportação da nota devolvia a marcação para o padrão.
CAMPOS_DE_CURADORIA_LOCAL = {"cancelada"}


@dataclass
class ResultadoGravacao:
    # `atualizadas` conta toda nota que JÁ EXISTIA e foi regravada com o dado do ADN —
    # não distingue se algum campo mudou de fato. É a semântica que o endpoint sempre
    # teve (e que `testar_upsert_nfse.py` fixa); o job a chama de "reconferida".
    importadas: int = 0
    atualizadas: int = 0
    erros: List[Dict] = field(default_factory=list)


def gravar_notas(db: Session, notas: Iterable[Dict],
                 dry_run: bool = False) -> ResultadoGravacao:
    """Cria ou atualiza cada nota, casando pela chave de acesso.

    NÃO faz commit: quem chama decide. O endpoint e o job commitam uma vez no fim, como o
    endpoint sempre fez. Com `dry_run`, só conta o que faria — não toca na sessão.
    """
    resultado = ResultadoGravacao()

    for nota_data in notas:
        try:
            # Identidade da nota = CHAVE DE ACESSO (50 dígitos), nunca o número.
            #
            # O número da NFS-e NÃO é único: em 18/06/2026 a emissão migrou para o
            # Emissor Nacional e a numeração REINICIOU (a série do Recife estava em
            # 5.723; a nacional recomeçou em 725). Casar por número fazia a nota nova
            # nº 749 encontrar a nota de 2019 nº 749 e sobrescrevê-la, em silêncio.
            # Impacto medido em 23/08/2026: ~280 notas de 2018-2021 já foram perdidas
            # dessa forma (faixa 725-1058), e outras 4.405 estavam na fila.
            # A chave de acesso (doc["ChaveAcesso"]) é única por documento fiscal.
            chave = nota_data.get('codigo_verificacao')
            if not chave:
                # Sem chave não há identidade confiável. Não inserir às cegas nem
                # cair de volta no número: pular e reportar.
                resultado.erros.append({
                    "nfse": nota_data.get('numero_nfse'),
                    "erro": "NFS-e sem chave de acesso; ignorada para não arriscar "
                            "sobrescrever outra nota"
                })
                continue

            nota_existente = db.query(NotaServicoModel).filter(
                NotaServicoModel.codigo_verificacao == chave
            ).first()

            if nota_existente:
                # Atualiza nota existente, preservando os campos de curadoria nossa
                if not dry_run:
                    for key, value in nota_data.items():
                        if key in CAMPOS_DE_CURADORIA_LOCAL:
                            continue
                        if hasattr(nota_existente, key):
                            setattr(nota_existente, key, value)
                resultado.atualizadas += 1
            else:
                # Cria nova nota. Os campos de curadoria começam no padrão do
                # modelo (cancelada=False) e só mudam por ação nossa.
                if not dry_run:
                    db.add(NotaServicoModel(**{
                        k: v for k, v in nota_data.items()
                        if k not in CAMPOS_DE_CURADORIA_LOCAL
                    }))
                resultado.importadas += 1

        except Exception as e:
            resultado.erros.append({
                "nfse": nota_data.get('numero_nfse'),
                "erro": str(e)
            })
            logger.exception("Erro ao processar NFSe %s: %s", nota_data.get('numero_nfse'), e)

    return resultado
