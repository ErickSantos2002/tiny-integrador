"""Extrator de notas fiscais do Tiny para o schema `tiny` (bronze).

Substitui o fluxo `[DATACORE] Puxar_Notas` do n8n, que tinha dois defeitos medidos em
2026-09-01 e corrigidos aqui:

* **marcador nunca chegava direito.** O n8n lia `marcadores.marcador.descricao` do XML;
  com dois ou mais marcadores aquilo é uma lista e a leitura dava `undefined`. Aqui a
  origem é JSON, onde `marcadores` é sempre lista. Ver `tiny_api`.
* **marcador posto depois da carga nunca entrava.** O ramo de atualização do n8n só
  disparava quando 31 campos da nota diferiam, e marcador não era nenhum deles — mas
  marcador é sempre posterior (nota é cancelada dias depois de emitida). Aqui os filhos
  da nota são sincronizados em toda passagem, sem depender de a nota ter mudado.

O custo dessa correção foi medido: 11 notas contavam como venda sem dever, R$ 226.685.

Regra de convivência: o que é **curadoria nossa** (`CAMPOS_DE_CURADORIA_LOCAL`) nunca é
sobrescrito pela importação. Mesma proteção que existe em `endpoints/nota_servico.py`.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.cliente import Cliente
from app.models.endereco_entrega import EnderecoEntrega
from app.models.forma_envio import FormaEnvio
from app.models.item_nota import ItemNota
from app.models.marcador import Marcador
from app.models.nota_fiscal import NotaFiscal

logger = logging.getLogger(__name__)

# Preenchido à mão pelo pessoal (PATCH /notas_fiscais/{id}/tipo). A origem não conhece
# esse campo; se a importação o escrevesse, apagaria a classificação a cada passagem.
CAMPOS_DE_CURADORIA_LOCAL = {"tipo"}

# Colunas da nota que vêm da origem, e de onde cada uma sai no JSON da api2.
# Só o que muda de nome fica explícito; o resto é campo de mesmo nome.
CAMPOS_DA_NOTA = [
    "tipo_nota", "natureza_operacao", "regime_tributario", "finalidade", "serie",
    "numero", "numero_ecommerce", "frete_por_conta", "condicao_pagamento",
    "forma_pagamento", "meio_pagamento", "id_vendedor", "nome_vendedor", "situacao",
    "descricao_situacao", "chave_acesso",
]
CAMPOS_NUMERICOS = [
    "base_icms", "valor_icms", "base_icms_st", "valor_icms_st", "valor_produtos",
    "valor_servicos", "valor_frete", "valor_seguro", "valor_outras", "valor_ipi",
    "valor_issqn", "valor_nota", "valor_desconto", "valor_faturado",
]
CAMPOS_DO_CLIENTE = [
    "nome", "cpf_cnpj", "tipo_pessoa", "ie", "endereco", "numero", "complemento",
    "bairro", "cep", "cidade", "uf", "fone", "email",
]
CAMPOS_DO_ENDERECO = [
    "cpf_cnpj", "nome_destinatario", "tipo_pessoa", "ie", "endereco", "numero",
    "complemento", "bairro", "cep", "cidade", "uf", "fone",
]
CAMPOS_DO_ITEM = [
    "id_produto", "codigo", "descricao", "unidade", "ncm", "cfop", "natureza",
]


# --------------------------------------------------------------------- conversões

def _txt(valor: Any) -> Optional[str]:
    """String vazia da API vira NULL. `''` e `None` significam a mesma coisa lá."""
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _num(valor: Any) -> Optional[Decimal]:
    """A api2 manda todo número como string ('3306.00'). Decimal, nunca float: isto é dinheiro."""
    texto = _txt(valor)
    if texto is None:
        return None
    try:
        return Decimal(texto.replace(",", "."))
    except InvalidOperation:
        logger.warning("valor numérico não reconhecido: %r", valor)
        return None


def _data(valor: Any) -> Optional[date]:
    texto = _txt(valor)
    if texto is None:
        return None
    try:
        return datetime.strptime(texto, "%d/%m/%Y").date()
    except ValueError:
        logger.warning("data não reconhecida: %r", valor)
        return None


def _hora(valor: Any) -> Optional[time]:
    texto = _txt(valor)
    if texto is None:
        return None
    for formato in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(texto, formato).time()
        except ValueError:
            continue
    logger.warning("hora não reconhecida: %r", valor)
    return None


def _lista(valor: Any, chave: str) -> list[dict]:
    """Normaliza as duas formas que a api2 usa para coleção.

    `itens` vem embrulhado (`[{"item": {...}}]`) e `marcadores` vem plano
    (`[{"id": ..., "descricao": ...}]`). Aceitar os dois evita depender de qual é qual.
    """
    saida = []
    for elemento in valor or []:
        if isinstance(elemento, dict):
            interno = elemento.get(chave, elemento)
            if isinstance(interno, dict):
                saida.append(interno)
    return saida


# ------------------------------------------------------------------- normalização

def normalizar_nota(nf: dict) -> dict:
    """Campos da nota prontos para o banco — sem cliente, sem filhos."""
    dados = {"id_tiny": _txt(nf.get("id"))}
    for campo in CAMPOS_DA_NOTA:
        dados[campo] = _txt(nf.get(campo))
    for campo in CAMPOS_NUMERICOS:
        dados[campo] = _num(nf.get(campo))
    dados["data_emissao"] = _data(nf.get("data_emissao"))
    dados["data_saida"] = _data(nf.get("data_saida"))
    dados["hora_saida"] = _hora(nf.get("hora_saida"))
    dados["observacoes"] = _txt(nf.get("obs"))  # a origem chama de `obs`
    return dados


def normalizar_cliente(nf: dict) -> Optional[dict]:
    cliente = nf.get("cliente") or {}
    dados = {campo: _txt(cliente.get(campo)) for campo in CAMPOS_DO_CLIENTE}
    # `cpf_cnpj` é a chave única da tabela: sem ele não há como casar nem deduplicar.
    return dados if dados.get("cpf_cnpj") else None


def normalizar_endereco(nf: dict) -> Optional[dict]:
    endereco = nf.get("endereco_entrega") or {}
    dados = {campo: _txt(endereco.get(campo)) for campo in CAMPOS_DO_ENDERECO}
    return dados if any(dados.values()) else None


def normalizar_envio(nf: dict) -> Optional[dict]:
    envio = nf.get("forma_envio") or {}  # a chave existe valendo null quando não há envio
    dados = {"id_forma": _txt(envio.get("id")), "descricao": _txt(envio.get("descricao"))}
    return dados if any(dados.values()) else None


def normalizar_marcadores(nf: dict) -> list[dict]:
    saida = []
    for m in _lista(nf.get("marcadores"), "marcador"):
        descricao = _txt(m.get("descricao"))
        if descricao:  # marcador sem descrição é linha-fantasma: o n8n gravava 7.7 mil delas
            saida.append({
                "id_marcador": _txt(m.get("id")),
                "descricao": descricao,
                "cor": _txt(m.get("cor")),
            })
    return saida


def normalizar_itens(nf: dict) -> list[dict]:
    saida = []
    for item in _lista(nf.get("itens"), "item"):
        dados = {campo: _txt(item.get(campo)) for campo in CAMPOS_DO_ITEM}
        dados["quantidade"] = _num(item.get("quantidade"))
        dados["valor_unitario"] = _num(item.get("valor_unitario"))
        dados["valor_total"] = _num(item.get("valor_total"))
        saida.append(dados)
    return saida


# ---------------------------------------------------------------------- gravação

def _comparavel(valor: Any) -> Any:
    """Forma canônica de um valor, para comparar filho do banco com filho da origem.

    Mesmo motivo de `_equivalente`, aplicado a item e marcador: `''` e NULL são a mesma
    ausência, e `Decimal("1.0000")` e `Decimal("1.00")` são a mesma quantidade. Sem isto,
    a sincronização apagaria e regravaria os filhos de todas as notas em toda passagem.
    """
    if valor is None:
        return None
    if isinstance(valor, Decimal):
        return valor.normalize()
    if isinstance(valor, str):
        return valor.strip() or None
    return valor


def _equivalente(atual: Any, novo: Any) -> bool:
    """Diz se dois valores significam a mesma coisa, ainda que não sejam idênticos.

    O n8n gravava o texto cru da API: string vazia em vez de NULL, e espaço em branco
    sobrando no fim (`natureza_operacao` com um espaço, `observacoes` terminando em
    `\n\r\n`). Este extrator normaliza na entrada — o que é melhor, mas faria toda nota
    do banco parecer "mudada" na primeira passagem, e uma atualização de verdade sumiria
    no meio de 8 mil reescritas cosméticas.

    Então a comparação é tolerante e a gravação é limpa: nota que só difere em espaço ou
    em vazio-vs-NULL fica quieta; quando escrever por um motivo real, escreve normalizado.
    Padronizar o que já está gravado é trabalho da silver (`lower(trim())`), não da bronze.
    """
    if isinstance(atual, str) or isinstance(novo, str):
        a = (atual or "").strip() if isinstance(atual, str) else ("" if atual is None else atual)
        b = (novo or "").strip() if isinstance(novo, str) else ("" if novo is None else novo)
        return a == b
    if atual is None or novo is None:
        return atual is None and novo is None
    return atual == novo


def _diferencas(objeto, dados: dict) -> dict:
    """Campos em que o banco discorda da origem, ignorando a curadoria local."""
    mudancas = {}
    for campo, novo in dados.items():
        if campo in CAMPOS_DE_CURADORIA_LOCAL:
            continue
        atual = getattr(objeto, campo, None)
        if not _equivalente(atual, novo):
            mudancas[campo] = (atual, novo)
    return mudancas


def garantir_cliente(db: Session, dados: Optional[dict]) -> Optional[int]:
    """Devolve o id do cliente, criando-o se for a primeira nota dele.

    Cliente **existente não é atualizado**, que é como o n8n sempre se comportou. Mudar
    isso aqui reescreveria o cadastro de 2.067 pessoas numa passagem, sem ninguém ter
    pedido. A limpeza e a deduplicação de cliente são trabalho da silver (Fase 4.4), com
    regra de sobrevivência escrita.
    """
    if not dados:
        return None
    cliente = db.query(Cliente).filter(Cliente.cpf_cnpj == dados["cpf_cnpj"]).one_or_none()
    if cliente is None:
        cliente = Cliente(**dados)
        db.add(cliente)
        db.flush()  # precisa do id agora para amarrar a nota
    return cliente.id


def _filhos_divergem(db: Session, modelo, id_nota: int, campos: list[str],
                     desejados: list[dict]) -> Optional[tuple[list, int, int]]:
    """Compara os filhos gravados com os da origem. Devolve (atuais, antes, depois) se difere."""
    atuais = db.query(modelo).filter(modelo.id_nota == id_nota).all()

    def chave(dados: dict) -> tuple:
        return tuple(_comparavel(dados.get(c)) for c in campos)

    antes = sorted(chave({c: getattr(o, c) for c in campos}) for o in atuais)
    depois = sorted(chave(d) for d in desejados)
    if antes == depois:
        return None
    return atuais, len(atuais), len(desejados)


def _sincronizar_filhos(db: Session, modelo, id_nota: int, campos: list[str],
                        desejados: list[dict]) -> Optional[tuple[int, int]]:
    """Deixa os filhos da nota iguais aos da origem. Devolve (antes, depois) se mudou.

    Apaga e regrava em vez de tentar casar linha a linha: nenhuma dessas tabelas tem
    chave de negócio (só um `id` serial), então não existe em que casar. E a origem é a
    verdade — marcador retirado no Tiny tem que sumir aqui. O histórico de "já esteve
    marcada" fica no snapshot do dbt (Fase 5.4), não na bronze.
    """
    divergencia = _filhos_divergem(db, modelo, id_nota, campos, desejados)
    if divergencia is None:
        return None
    atuais, antes, depois = divergencia

    for obsoleto in atuais:
        db.delete(obsoleto)
    db.flush()
    for dados in desejados:
        db.add(modelo(id_nota=id_nota, **dados))
    return antes, depois


def salvar_nota(db: Session, nf: dict, *, dry_run: bool = False) -> dict:
    """Grava uma nota e tudo que pende dela. Uma transação por nota.

    O relatório devolvido é o mesmo em `dry_run`: dá para conferir o que aconteceria
    antes de deixar escrever.
    """
    dados = normalizar_nota(nf)
    marcadores = normalizar_marcadores(nf)
    itens = normalizar_itens(nf)
    endereco = normalizar_endereco(nf)
    envio = normalizar_envio(nf)

    relato: dict[str, Any] = {
        "id_tiny": dados["id_tiny"],
        "numero": dados["numero"],
        "data_emissao": dados["data_emissao"],
        "marcadores": [m["descricao"] for m in marcadores],
        "itens": len(itens),
        "mudancas": {},
        "filhos": {},
    }

    nota = db.query(NotaFiscal).filter(NotaFiscal.id_tiny == dados["id_tiny"]).one_or_none()

    filhos = [
        ("marcadores", Marcador, ["id_marcador", "descricao", "cor"], marcadores),
        ("itens", ItemNota, CAMPOS_DO_ITEM + ["quantidade", "valor_unitario", "valor_total"], itens),
        ("endereco", EnderecoEntrega, CAMPOS_DO_ENDERECO, [endereco] if endereco else []),
        ("envio", FormaEnvio, ["id_forma", "descricao"], [envio] if envio else []),
    ]

    if dry_run:
        if nota is None:
            relato["acao"] = "criaria"
            return relato
        relato["mudancas"] = _diferencas(nota, dados)
        for nome, modelo, campos, desejados in filhos:
            divergencia = _filhos_divergem(db, modelo, nota.id, campos, desejados)
            if divergencia:
                relato["filhos"][nome] = divergencia[1:]
        relato["acao"] = ("atualizaria" if relato["mudancas"]
                          else "atualizaria filhos" if relato["filhos"]
                          else "inalterada")
        return relato

    try:
        id_cliente = garantir_cliente(db, normalizar_cliente(nf))

        if nota is None:
            nota = NotaFiscal(**dados, id_cliente=id_cliente)
            db.add(nota)
            db.flush()
            relato["acao"] = "criada"
        else:
            mudancas = _diferencas(nota, dados)
            for campo, (_, novo) in mudancas.items():
                setattr(nota, campo, novo)
            if id_cliente and nota.id_cliente != id_cliente:
                nota.id_cliente = id_cliente
            relato["acao"] = "atualizada" if mudancas else "inalterada"
            relato["mudancas"] = {c: v for c, v in mudancas.items()}

        for nome, modelo, campos, desejados in filhos:
            mudou = _sincronizar_filhos(db, modelo, nota.id, campos, desejados)
            if mudou:
                relato["filhos"][nome] = mudou

        db.commit()
    except Exception:
        db.rollback()
        raise

    if relato["acao"] == "inalterada" and relato["filhos"]:
        relato["acao"] = "filhos atualizados"
    return relato
