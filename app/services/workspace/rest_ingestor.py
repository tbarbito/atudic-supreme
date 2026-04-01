# -*- coding: utf-8 -*-
"""Ingestor REST — transforma dados da API REST do Protheus no formato do workspace SQLite.

Mesma interface de progresso do Ingestor CSV (AsyncGenerator de dicts),
mesmos INSERT statements, mesmas chaves de dict.
"""

import logging
import re
from typing import AsyncGenerator

from app.services.workspace.workspace_db import Database
from app.services.workspace.rest_client import ProtheusRESTClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_int(val) -> int:
    """Converte valor para int de forma segura (aceita str, int, float, None)."""
    try:
        return int(str(val).strip() or "0")
    except (ValueError, TypeError):
        return 0


def _s(item: dict, key: str) -> str:
    """Extrai string de um item REST, tratando None, int e espaços."""
    val = item.get(key)
    if val is None:
        return ""
    return str(val).strip()


def _is_custom_table(codigo: str) -> bool:
    """Detecta tabela custom — mesma logica de parser_sx.py."""
    if re.match(r"^SZ[0-9A-Z]$", codigo):
        return True
    if re.match(r"^Q[A-Z][0-9A-Z]$", codigo):
        return True
    if re.match(r"^Z[0-9A-Z][0-9A-Z]?$", codigo):
        return True
    return False


def _is_custom_field(campo: str) -> bool:
    """Detecta campo custom — mesma logica de parser_sx.py."""
    parts = campo.split("_")
    if len(parts) >= 2 and parts[1].startswith("X"):
        return True
    return False


# ---------------------------------------------------------------------------
# Transformadores REST → formato workspace dict
# ---------------------------------------------------------------------------

def _transform_sx2(item: dict) -> dict | None:
    """REST item → formato tabelas (SX2)."""
    codigo = _s(item, "x2_chave")
    if not codigo:
        return None
    return {
        "codigo": codigo,
        "nome": _s(item, "x2_nome"),
        "modo": _s(item, "x2_modo"),
        "custom": 1 if _is_custom_table(codigo) else 0,
    }


def _transform_sx3(item: dict) -> dict | None:
    """REST item → formato campos (SX3)."""
    campo = _s(item, "x3_campo")
    if not campo:
        return None

    proprietario = _s(item, "x3_propri") or "S"
    is_custom = 1 if _is_custom_field(campo) else 0
    if proprietario and proprietario != "S":
        is_custom = 1

    # Obrigatorio: mesma logica do parser_sx.py (mask 'x', ou 'S', 'SIM', '1', '.T.')
    obrig_raw = _s(item, "x3_obrigat")
    obrigatorio = 1 if (
        obrig_raw.lower().startswith("x")
        or obrig_raw.upper() in ("S", "SIM", "1", ".T.")
    ) else 0

    return {
        "tabela": _s(item, "x3_arquivo"),
        "campo": campo,
        "tipo": _s(item, "x3_tipo"),
        "tamanho": _safe_int(item.get("x3_tamanho", "0")),
        "decimal": _safe_int(item.get("x3_decimal", "0")),
        "titulo": _s(item, "x3_titulo"),
        "descricao": _s(item, "x3_descric"),
        "validacao": _s(item, "x3_valid"),
        "inicializador": _s(item, "x3_relacao"),
        "obrigatorio": obrigatorio,
        "custom": is_custom,
        "f3": _s(item, "x3_f3"),
        "cbox": _s(item, "x3_cbox"),
        "vlduser": _s(item, "x3_vlduser"),
        "when_expr": _s(item, "x3_when"),
        "proprietario": proprietario,
        "browse": _s(item, "x3_browse"),
        "trigger_flag": _s(item, "x3_trigger"),
        "visual": _s(item, "x3_visual"),
        "context": _s(item, "x3_context"),
        "folder": _s(item, "x3_folder"),
        "grpsxg": _s(item, "x3_grpsxg"),
    }


def _transform_six(item: dict) -> dict | None:
    """REST item → formato indices (SIX).

    API REST retorna campos com prefixo minusculo do SIX.
    SIX no Protheus usa colunas SEM prefixo (INDICE, ORDEM, etc.),
    mas via REST chegam como indice, ordem, chave, descricao, propri, etc.
    """
    tabela = _s(item, "indice")
    ordem = _s(item, "ordem")
    if not tabela or not ordem:
        return None
    proprietario = _s(item, "propri")
    return {
        "tabela": tabela,
        "ordem": ordem,
        "chave": _s(item, "chave"),
        "descricao": _s(item, "descricao"),
        "proprietario": proprietario,
        "f3": _s(item, "f3"),
        "nickname": _s(item, "nickname"),
        "showpesq": _s(item, "showpesq"),
        "custom": 1 if proprietario and proprietario != "S" else 0,
    }


def _transform_sx7(item: dict) -> dict | None:
    """REST item → formato gatilhos (SX7)."""
    campo_origem = _s(item, "x7_campo")
    if not campo_origem:
        return None
    campo_destino = _s(item, "x7_cdomin")
    proprietario = _s(item, "x7_propri")
    is_custom = 1 if _is_custom_field(campo_destino) else 0
    if proprietario and proprietario != "S":
        is_custom = 1
    return {
        "campo_origem": campo_origem,
        "sequencia": _s(item, "x7_sequenc"),
        "campo_destino": campo_destino,
        "regra": _s(item, "x7_regra"),
        "tipo": _s(item, "x7_tipo"),
        "tabela": _s(item, "x7_alias") or _s(item, "x7_arquivo"),
        "condicao": _s(item, "x7_condic"),
        "proprietario": proprietario,
        "seek": _s(item, "x7_seek"),
        "alias": _s(item, "x7_alias"),
        "ordem": _s(item, "x7_ordem"),
        "chave": _s(item, "x7_chave"),
        "custom": is_custom,
    }


def _transform_sx1(item: dict) -> dict | None:
    """REST item → formato perguntas (SX1)."""
    grupo = _s(item, "x1_grupo")
    ordem = _s(item, "x1_ordem")
    if not grupo or not ordem:
        return None
    return {
        "grupo": grupo,
        "ordem": ordem,
        "pergunta": _s(item, "x1_pergunt"),
        "variavel": _s(item, "x1_variavl"),
        "tipo": _s(item, "x1_tipo"),
        "tamanho": _safe_int(item.get("x1_tamanho", "0")),
        "decimal": _safe_int(item.get("x1_decimal", "0")),
        "f3": _s(item, "x1_f3"),
        "validacao": _s(item, "x1_valid"),
        "conteudo_padrao": _s(item, "x1_def01"),
    }


def _transform_sx5(item: dict) -> dict | None:
    """REST item → formato tabelas_genericas (SX5)."""
    tabela = _s(item, "x5_tabela")
    chave = _s(item, "x5_chave")
    if not tabela or not chave:
        return None
    return {
        "filial": _s(item, "x5_filial"),
        "tabela": tabela,
        "chave": chave,
        "descricao": _s(item, "x5_descri"),
        "custom": 1 if tabela.startswith("Z") or tabela.startswith("X") else 0,
    }


def _transform_sx6(item: dict) -> dict | None:
    """REST item → formato parametros (SX6)."""
    variavel = _s(item, "x6_var")
    if not variavel:
        return None
    descricao = (_s(item, "x6_descric") + " " + _s(item, "x6_desc1")).strip()
    proprietario = _s(item, "x6_propri")
    return {
        "filial": _s(item, "x6_fil"),
        "variavel": variavel,
        "tipo": _s(item, "x6_tipo"),
        "descricao": descricao,
        "conteudo": _s(item, "x6_conteud"),
        "proprietario": proprietario,
        "custom": 1 if proprietario != "S" else 0,
    }


def _transform_sx9(item: dict) -> dict | None:
    """REST item → formato relacionamentos (SX9)."""
    tabela_origem = _s(item, "x9_dom")
    tabela_destino = _s(item, "x9_cdom")
    if not tabela_origem or not tabela_destino:
        return None
    proprietario = _s(item, "x9_propri")
    return {
        "tabela_origem": tabela_origem,
        "identificador": _s(item, "x9_ident"),
        "tabela_destino": tabela_destino,
        "expressao_origem": _s(item, "x9_expdom"),
        "expressao_destino": _s(item, "x9_expcdom"),
        "proprietario": proprietario,
        "condicao_sql": _s(item, "x9_condsql"),
        "custom": 1 if proprietario != "S" else 0,
    }


def _transform_sxa(item: dict) -> dict | None:
    """REST item → formato pastas (SXA)."""
    alias = _s(item, "xa_alias")
    ordem = _s(item, "xa_ordem")
    if not alias or not ordem:
        return None
    return {
        "alias": alias,
        "ordem": ordem,
        "descricao": _s(item, "xa_descric"),
        "proprietario": _s(item, "xa_propri"),
        "agrupamento": _s(item, "xa_agrup"),
    }


def _transform_sxb(item: dict) -> dict | None:
    """REST item → formato consultas (SXB)."""
    alias = _s(item, "xb_alias")
    sequencia = _s(item, "xb_seq")
    if not alias or not sequencia:
        return None
    return {
        "alias": alias,
        "tipo": _s(item, "xb_tipo"),
        "sequencia": sequencia,
        "coluna": _s(item, "xb_coluna"),
        "descricao": _s(item, "xb_descri"),
        "conteudo": _s(item, "xb_contem"),
    }


# ---------------------------------------------------------------------------
# Mapeamento SX → funcao de transformacao
# ---------------------------------------------------------------------------

def _transform_sxg(item: dict) -> dict | None:
    """REST item -> formato grupos_campo (SXG)."""
    grupo = _s(item, "xg_grupo")
    if not grupo:
        return None
    return {
        "grupo": grupo,
        "descricao": _s(item, "xg_descri"),
        "tamanho_max": _safe_int(item.get("xg_sizemax", 0)),
        "tamanho_min": _safe_int(item.get("xg_sizemin", 0)),
        "tamanho": _safe_int(item.get("xg_size", 0)),
    }


_SX_TRANSFORMS = {
    "SX2": _transform_sx2,
    "SX3": _transform_sx3,
    "SIX": _transform_six,
    "SX7": _transform_sx7,
    "SX1": _transform_sx1,
    "SX5": _transform_sx5,
    "SX6": _transform_sx6,
    "SX9": _transform_sx9,
    "SXA": _transform_sxa,
    "SXB": _transform_sxb,
    "SXG": _transform_sxg,
}


# ---------------------------------------------------------------------------
# RESTIngestor
# ---------------------------------------------------------------------------

class RESTIngestor:
    """Ingestor via REST API — mesma interface de progresso do Ingestor CSV.

    Busca cada tabela SX via ProtheusRESTClient, transforma no formato
    workspace e grava no SQLite usando os mesmos INSERT statements do
    Ingestor CSV original.
    """

    def __init__(self, db: Database, client: ProtheusRESTClient):
        self.db = db
        self.client = client

    async def run_fase1(self) -> AsyncGenerator[dict, None]:
        """Fase 1: Ingestao do dicionario via REST API.

        Busca SX2, SX3, SIX, SX7, SX1, SX5, SX6, SX9, SXA, SXB via REST.
        Transforma no formato workspace e alimenta _store_sx().
        Yields progresso no mesmo formato do Ingestor CSV.
        """
        sx_tables = list(_SX_TRANSFORMS.items())

        for sx_name, transform_fn in sx_tables:
            try:
                logger.info("REST ingestao: buscando %s...", sx_name)
                yield {
                    "fase": 1,
                    "item": sx_name,
                    "status": "fetching",
                    "msg": f"Buscando {sx_name} via REST...",
                }

                raw_items = self.client.query_sx_table(sx_name)
                logger.info("REST ingestao: %s retornou %d registros brutos", sx_name, len(raw_items))

                # Transformar e filtrar registros invalidos (None)
                rows = []
                for item in raw_items:
                    if not item:
                        continue
                    transformed = transform_fn(item)
                    if transformed:
                        rows.append(transformed)

                # Gravar no SQLite
                if rows:
                    self._store_sx(sx_name, rows)

                # Registrar progresso
                self.db.execute(
                    "INSERT OR REPLACE INTO ingest_progress (item, fase, status) "
                    "VALUES (?, 1, 'done')",
                    (f"{sx_name}_rest",),
                )
                self.db.commit()

                logger.info("REST ingestao: %s concluido — %d registros gravados", sx_name, len(rows))
                yield {
                    "fase": 1,
                    "item": sx_name,
                    "status": "done",
                    "count": len(rows),
                }

            except Exception as e:
                logger.error("Erro REST ingestao %s: %s", sx_name, e, exc_info=True)
                self.db.execute(
                    "INSERT OR REPLACE INTO ingest_progress (item, fase, status, error_msg) "
                    "VALUES (?, 1, 'error', ?)",
                    (f"{sx_name}_rest", str(e)),
                )
                self.db.commit()
                yield {
                    "fase": 1,
                    "item": sx_name,
                    "status": "error",
                    "msg": str(e),
                }

    def _store_sx(self, sx_name: str, rows: list[dict]):
        """Grava registros no workspace SQLite.

        Usa EXATAMENTE os mesmos INSERT statements do Ingestor CSV
        (ingestor.py _store_sx, linhas 323-353) para garantir compatibilidade
        total com o schema do workspace.
        """
        if sx_name == "SX2":
            self.db.executemany(
                "INSERT OR REPLACE INTO tabelas (codigo, nome, modo, custom) "
                "VALUES (:codigo, :nome, :modo, :custom)", rows)
        elif sx_name == "SX3":
            self.db.executemany(
                "INSERT OR REPLACE INTO campos (tabela, campo, tipo, tamanho, decimal, "
                "titulo, descricao, validacao, inicializador, obrigatorio, custom, f3, "
                "cbox, vlduser, when_expr, proprietario, browse, trigger_flag, visual, "
                "context, folder, grpsxg) VALUES (:tabela, :campo, :tipo, :tamanho, "
                ":decimal, :titulo, :descricao, :validacao, :inicializador, :obrigatorio, "
                ":custom, :f3, :cbox, :vlduser, :when_expr, :proprietario, :browse, "
                ":trigger_flag, :visual, :context, :folder, :grpsxg)", rows)
        elif sx_name == "SIX":
            self.db.executemany(
                "INSERT OR REPLACE INTO indices (tabela, ordem, chave, descricao, "
                "proprietario, f3, nickname, showpesq, custom) VALUES (:tabela, :ordem, "
                ":chave, :descricao, :proprietario, :f3, :nickname, :showpesq, :custom)", rows)
        elif sx_name == "SX7":
            self.db.executemany(
                "INSERT OR REPLACE INTO gatilhos (campo_origem, sequencia, campo_destino, "
                "regra, tipo, tabela, condicao, proprietario, seek, alias, ordem, chave, "
                "custom) VALUES (:campo_origem, :sequencia, :campo_destino, :regra, :tipo, "
                ":tabela, :condicao, :proprietario, :seek, :alias, :ordem, :chave, :custom)", rows)
        elif sx_name == "SX1":
            self.db.executemany(
                "INSERT OR REPLACE INTO perguntas (grupo, ordem, pergunta, variavel, tipo, "
                "tamanho, decimal, f3, validacao, conteudo_padrao) VALUES (:grupo, :ordem, "
                ":pergunta, :variavel, :tipo, :tamanho, :decimal, :f3, :validacao, "
                ":conteudo_padrao)", rows)
        elif sx_name == "SX5":
            self.db.executemany(
                "INSERT OR REPLACE INTO tabelas_genericas (filial, tabela, chave, descricao, "
                "custom) VALUES (:filial, :tabela, :chave, :descricao, :custom)", rows)
        elif sx_name == "SX6":
            self.db.executemany(
                "INSERT OR REPLACE INTO parametros (filial, variavel, tipo, descricao, "
                "conteudo, proprietario, custom) VALUES (:filial, :variavel, :tipo, "
                ":descricao, :conteudo, :proprietario, :custom)", rows)
        elif sx_name == "SX9":
            self.db.executemany(
                "INSERT OR REPLACE INTO relacionamentos (tabela_origem, identificador, "
                "tabela_destino, expressao_origem, expressao_destino, proprietario, "
                "condicao_sql, custom) VALUES (:tabela_origem, :identificador, "
                ":tabela_destino, :expressao_origem, :expressao_destino, :proprietario, "
                ":condicao_sql, :custom)", rows)
        elif sx_name == "SXA":
            self.db.executemany(
                "INSERT OR REPLACE INTO pastas (alias, ordem, descricao, proprietario, "
                "agrupamento) VALUES (:alias, :ordem, :descricao, :proprietario, "
                ":agrupamento)", rows)
        elif sx_name == "SXB":
            self.db.executemany(
                "INSERT OR REPLACE INTO consultas (alias, tipo, sequencia, coluna, "
                "descricao, conteudo) VALUES (:alias, :tipo, :sequencia, :coluna, "
                ":descricao, :conteudo)", rows)
        elif sx_name == "SXG":
            # Contar campos por grupo apos SX3 ja ter sido ingerido
            conn = self.db.get_raw_conn()
            for row in rows:
                try:
                    total = conn.execute(
                        "SELECT COUNT(*) FROM campos WHERE grpsxg=?", (row["grupo"],)
                    ).fetchone()[0]
                    row["total_campos"] = total
                except Exception:
                    row["total_campos"] = 0
            self.db.executemany(
                "INSERT OR REPLACE INTO grupos_campo (grupo, descricao, tamanho_max, "
                "tamanho_min, tamanho, total_campos) VALUES (:grupo, :descricao, "
                ":tamanho_max, :tamanho_min, :tamanho, :total_campos)", rows)

        self.db.commit()
