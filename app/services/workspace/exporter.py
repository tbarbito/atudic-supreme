# -*- coding: utf-8 -*-
"""
Exporter — Exporta dados do workspace em formatos CSV/JSON/YAML.

Formatos suportados:
- CSV: Importavel no Protheus via APSDU/tools
- JSON: Formato AtuDic para ingestao
- YAML: Formato legivel para revisao humana
"""

import csv
import io
import json
import logging
from typing import Optional

from app.services.workspace.workspace_db import Database
from app.services.workspace.knowledge import KnowledgeService

logger = logging.getLogger(__name__)


class WorkspaceExporter:
    """Exporta dados do workspace em multiplos formatos."""

    def __init__(self, db: Database):
        self.db = db
        self.ks = KnowledgeService(db)

    # ========================================================================
    # CSV EXPORTS
    # ========================================================================

    def export_campos_custom_csv(self, tabela: Optional[str] = None) -> str:
        """Exporta campos customizados em CSV."""
        if tabela:
            rows = self.db.execute(
                "SELECT tabela, campo, tipo, tamanho, decimal, titulo, descricao, "
                "validacao, inicializador, obrigatorio, f3, cbox, vlduser, proprietario "
                "FROM campos WHERE custom = 1 AND tabela = ? ORDER BY tabela, campo",
                (tabela.upper(),)
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT tabela, campo, tipo, tamanho, decimal, titulo, descricao, "
                "validacao, inicializador, obrigatorio, f3, cbox, vlduser, proprietario "
                "FROM campos WHERE custom = 1 ORDER BY tabela, campo"
            ).fetchall()

        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")
        writer.writerow([
            "X3_ARQUIVO", "X3_CAMPO", "X3_TIPO", "X3_TAMANHO", "X3_DECIMAL",
            "X3_TITULO", "X3_DESCRIC", "X3_VALID", "X3_RELACAO", "X3_OBRIGAT",
            "X3_F3", "X3_CBOX", "X3_VLDUSER", "X3_PROPRI",
        ])
        for r in rows:
            writer.writerow(r)
        return output.getvalue()

    def export_indices_custom_csv(self, tabela: Optional[str] = None) -> str:
        """Exporta indices customizados em CSV."""
        if tabela:
            rows = self.db.execute(
                "SELECT tabela, ordem, chave, descricao, proprietario "
                "FROM indices WHERE custom = 1 AND tabela = ? ORDER BY tabela, ordem",
                (tabela.upper(),)
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT tabela, ordem, chave, descricao, proprietario "
                "FROM indices WHERE custom = 1 ORDER BY tabela, ordem"
            ).fetchall()

        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")
        writer.writerow(["INDICE", "ORDEM", "CHAVE", "DESCRICAO", "PROPRI"])
        for r in rows:
            writer.writerow(r)
        return output.getvalue()

    def export_gatilhos_custom_csv(self) -> str:
        """Exporta gatilhos customizados em CSV."""
        rows = self.db.execute(
            "SELECT campo_origem, sequencia, campo_destino, regra, tipo, "
            "tabela, condicao, proprietario, seek, alias, ordem, chave "
            "FROM gatilhos WHERE custom = 1 ORDER BY campo_origem, sequencia"
        ).fetchall()

        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")
        writer.writerow([
            "X7_CAMPO", "X7_SEQUENC", "X7_CDOMIN", "X7_REGRA", "X7_TIPO",
            "X7_ALIAS", "X7_CONDIC", "X7_PROPRI", "X7_SEEK", "X7_ALIAS2",
            "X7_ORDEM", "X7_CHAVE",
        ])
        for r in rows:
            writer.writerow(r)
        return output.getvalue()

    # ========================================================================
    # JSON EXPORT (formato AtuDic)
    # ========================================================================

    def export_atudic_json(self, tabela: Optional[str] = None) -> dict:
        """Exporta em formato AtuDic JSON para ingestao no BiizHubOps."""
        result = {
            "format": "atudic-ingest",
            "version": "1.0",
            "source": "atudic-supreme-workspace",
        }

        # Tabelas
        if tabela:
            tab_info = self.ks.get_table_info(tabela.upper())
            result["tabelas"] = [tab_info] if tab_info else []
        else:
            rows = self.db.execute(
                "SELECT codigo, nome, modo, custom FROM tabelas WHERE custom = 1"
            ).fetchall()
            result["tabelas"] = [
                {"codigo": r[0], "nome": r[1], "modo": r[2], "custom": bool(r[3])}
                for r in rows
            ]

        # Campos custom
        campos_rows = self.db.execute(
            "SELECT tabela, campo, tipo, tamanho, decimal, titulo, descricao, "
            "validacao, inicializador, obrigatorio, f3, cbox, vlduser, when_expr, proprietario "
            "FROM campos WHERE custom = 1" +
            (" AND tabela = ?" if tabela else "") +
            " ORDER BY tabela, campo",
            (tabela.upper(),) if tabela else ()
        ).fetchall()
        result["campos"] = [
            {
                "tabela": r[0], "campo": r[1], "tipo": r[2], "tamanho": r[3],
                "decimal": r[4], "titulo": r[5], "descricao": r[6], "validacao": r[7],
                "inicializador": r[8], "obrigatorio": bool(r[9]), "f3": r[10],
                "cbox": r[11], "vlduser": r[12], "when_expr": r[13], "proprietario": r[14],
            }
            for r in campos_rows
        ]

        # Indices custom
        idx_rows = self.db.execute(
            "SELECT tabela, ordem, chave, descricao, proprietario "
            "FROM indices WHERE custom = 1" +
            (" AND tabela = ?" if tabela else "") +
            " ORDER BY tabela, ordem",
            (tabela.upper(),) if tabela else ()
        ).fetchall()
        result["indices"] = [
            {"tabela": r[0], "ordem": r[1], "chave": r[2], "descricao": r[3], "proprietario": r[4]}
            for r in idx_rows
        ]

        # Gatilhos custom
        gat_rows = self.db.execute(
            "SELECT campo_origem, sequencia, campo_destino, regra, tipo, "
            "condicao, proprietario FROM gatilhos WHERE custom = 1"
        ).fetchall()
        result["gatilhos"] = [
            {
                "campo_origem": r[0], "sequencia": r[1], "campo_destino": r[2],
                "regra": r[3], "tipo": r[4], "condicao": r[5], "proprietario": r[6],
            }
            for r in gat_rows
        ]

        result["totais"] = {
            "tabelas": len(result["tabelas"]),
            "campos": len(result["campos"]),
            "indices": len(result["indices"]),
            "gatilhos": len(result["gatilhos"]),
        }

        return result

    # ========================================================================
    # DIFF EXPORT
    # ========================================================================

    def export_diff_csv(self, tipo_sx: Optional[str] = None) -> str:
        """Exporta diff padrao x cliente em CSV."""
        if tipo_sx:
            rows = self.db.execute(
                "SELECT tipo_sx, tabela, chave, acao, campo_diff, valor_padrao, valor_cliente "
                "FROM diff WHERE tipo_sx = ? ORDER BY tabela, chave",
                (tipo_sx,)
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT tipo_sx, tabela, chave, acao, campo_diff, valor_padrao, valor_cliente "
                "FROM diff ORDER BY tipo_sx, tabela, chave"
            ).fetchall()

        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")
        writer.writerow(["TIPO_SX", "TABELA", "CHAVE", "ACAO", "CAMPO_DIFF", "VALOR_PADRAO", "VALOR_CLIENTE"])
        for r in rows:
            writer.writerow(r)
        return output.getvalue()
