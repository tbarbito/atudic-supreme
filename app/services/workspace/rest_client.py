# -*- coding: utf-8 -*-
"""Cliente REST para API do Protheus — coleta de dados para workspace.

Utiliza a API REST Framework do Protheus para buscar dicionario de dados (SX2, SX3, SIX, etc.)
e executar consultas genericas em tabelas do ERP.

Uso:
    client = ProtheusRESTClient("http://host:8019/rest", "admin", "1234")
    result = client.test_connection()
    if result["ok"]:
        tabelas = client.get_tables()
        campos = client.get_fields(table="SA1")
"""

import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

# ── Mapeamento de campos por tabela SX ──────────────────────────────────────

SX_FIELD_MAP = {
    "SX2": "X2_CHAVE,X2_NOME,X2_MODO,X2_UESSION",
    "SX3": (
        "X3_ARQUIVO,X3_CAMPO,X3_TIPO,X3_TAMANHO,X3_DECIMAL,X3_TITULO,X3_DESCRIC,"
        "X3_VALID,X3_RELACAO,X3_OBRIGAT,X3_PROPRI,X3_F3,X3_CBOX,X3_VLDUSER,"
        "X3_WHEN,X3_BROWSE,X3_TRIGGER,X3_VISUAL,X3_CONTEXT,X3_FOLDER,X3_GRPSXG"
    ),
    "SIX": "INDICE,ORDEM,CHAVE,DESCRICAO,PROPRI,F3,NICKNAME,SHOWPESQ",
    "SX7": (
        "X7_CAMPO,X7_SEQUENC,X7_CDOMIN,X7_REGRA,X7_TIPO,X7_TABELA,"
        "X7_CONDIC,X7_PROPRI,X7_SEEK,X7_ALIAS,X7_ORDEM,X7_CHAVE"
    ),
    "SX1": (
        "X1_GRUPO,X1_ORDEM,X1_PERGUNT,X1_VARIAVL,X1_TIPO,X1_TAMANHO,"
        "X1_DECIMAL,X1_F3,X1_VALID,X1_CNT01"
    ),
    "SX5": "X5_FILIAL,X5_TABELA,X5_CHAVE,X5_DESCRI",
    "SX6": "X6_FIL,X6_VAR,X6_TIPO,X6_DESCRIC,X6_CONTEUD,X6_PROPRI",
    "SX9": "X9_DOM,X9_IDENT,X9_EXPDOM,X9_EXPCOD,X9_PROPRI,X9_CDSQL",
    "SXA": "XA_ALIAS,XA_ORDEM,XA_DESCRI,XA_PROPRI,XA_AGRUPA",
    "SXB": "XB_ALIAS,XB_TIPO,XB_SEQ,XB_COLUNA,XB_DESCRI,XB_CONTEM",
    # SXG nao disponivel via genericQuery (tabela de sistema)
    # grupos_campo derivado do grpsxg dos campos (SX3) no rest_ingestor
}


class ProtheusRESTClient:
    """Cliente para API REST do Protheus com paginacao automatica."""

    def __init__(self, base_url: str, user: str, password: str, timeout: int = 30):
        """
        Args:
            base_url: URL base da API REST (ex: http://192.168.122.41:8019/rest)
            user: Usuario Protheus
            password: Senha
            timeout: Timeout em segundos por request
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.auth = (user, password)
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    # ── Conexao e saude ─────────────────────────────────────────────────

    def test_connection(self) -> dict:
        """Testa conexao com a API REST.

        Retorna:
            {"ok": True/False, "message": "...", "details": {...}}
        """
        try:
            resp = self._get(
                "/api/framework/v1/Dictionary/Tables",
                params={"pageSize": 1, "page": 1},
            )
            total = resp.get("total", 0)
            return {
                "ok": True,
                "message": f"Conexao OK — {total} tabela(s) no dicionario",
                "details": {"total_tables": total},
            }
        except requests.exceptions.ConnectionError as exc:
            msg = f"Erro de conexao com {self.base_url}: {exc}"
            logger.error(msg)
            return {"ok": False, "message": msg}
        except requests.exceptions.Timeout:
            msg = f"Timeout ao conectar em {self.base_url} ({self.timeout}s)"
            logger.error(msg)
            return {"ok": False, "message": msg}
        except requests.exceptions.HTTPError as exc:
            msg = f"Erro HTTP: {exc.response.status_code} — {exc.response.text[:200]}"
            logger.error(msg)
            return {"ok": False, "message": msg}
        except Exception as exc:
            msg = f"Erro inesperado ao testar conexao: {exc}"
            logger.error(msg)
            return {"ok": False, "message": msg}

    # ── Endpoints de dicionario ─────────────────────────────────────────

    def get_tables(self) -> list[dict]:
        """Lista todas as tabelas via Dictionary/Tables."""
        logger.info("Buscando tabelas (SX2) via Dictionary/Tables...")
        items = self._paginate("/api/framework/v1/Dictionary/Tables")
        logger.info("Dictionary/Tables retornou %d tabela(s)", len(items))
        return items

    def get_fields(self, table: Optional[str] = None) -> list[dict]:
        """Lista campos via Dictionary/Fields.

        Args:
            table: Se fornecido, filtra campos desta tabela (alias sem empresa/filial, ex: SA1).
        """
        params = {}
        if table:
            params["table"] = table.upper()
            logger.info("Buscando campos da tabela %s via Dictionary/Fields...", table)
        else:
            logger.info("Buscando todos os campos via Dictionary/Fields...")

        items = self._paginate("/api/framework/v1/Dictionary/Fields", params=params)
        logger.info("Dictionary/Fields retornou %d campo(s)", len(items))
        return items

    def get_indexes(self, table: Optional[str] = None) -> list[dict]:
        """Lista indices via Dictionary/Indexes.

        Args:
            table: Se fornecido, filtra indices desta tabela.
        """
        params = {}
        if table:
            params["table"] = table.upper()
            logger.info("Buscando indices da tabela %s via Dictionary/Indexes...", table)
        else:
            logger.info("Buscando todos os indices via Dictionary/Indexes...")

        items = self._paginate("/api/framework/v1/Dictionary/Indexes", params=params)
        logger.info("Dictionary/Indexes retornou %d indice(s)", len(items))
        return items

    def get_standard_queries(self) -> list[dict]:
        """Lista consultas padrao via Dictionary/StandardQuery."""
        logger.info("Buscando consultas padrao (SXB) via Dictionary/StandardQuery...")
        items = self._paginate("/api/framework/v1/Dictionary/StandardQuery")
        logger.info("Dictionary/StandardQuery retornou %d consulta(s)", len(items))
        return items

    # ── Consulta generica ───────────────────────────────────────────────

    def generic_query(
        self,
        table: str,
        fields: str,
        where: Optional[str] = None,
        order: Optional[str] = None,
        page_size: int = 100,
        max_pages: int = 50,
    ) -> list[dict]:
        """Consulta generica com paginacao automatica.

        Args:
            table: Alias da tabela (SA1, SB1, etc.)
            fields: Campos separados por virgula
            where: Filtro WHERE (sem a keyword WHERE)
            order: Campo(s) de ordenacao
            page_size: Registros por pagina
            max_pages: Limite de paginas (safety — evitar loops infinitos)

        Returns:
            Lista de dicts com os dados
        """
        params = {
            "tables": table.upper(),
            "fields": fields,
            "pageSize": page_size,
            "page": 1,
        }
        if where:
            params["where"] = where
        if order:
            params["order"] = order

        all_items = []
        page = 1

        while page <= max_pages:
            params["page"] = page
            resp = self._get("/api/framework/v1/genericQuery", params=params)

            items = resp.get("items", [])
            all_items.extend(items)

            # Log progresso a cada 5 paginas
            if page % 5 == 0:
                total = resp.get("total", "?")
                logger.info(
                    "genericQuery %s — pagina %d, %d registros acumulados (total: %s)",
                    table, page, len(all_items), total,
                )

            has_next = resp.get("hasNext", False)
            if not has_next:
                break

            page += 1

        if page > max_pages:
            logger.warning(
                "genericQuery %s atingiu limite de %d paginas (%d registros coletados). "
                "Pode haver dados faltando.",
                table, max_pages, len(all_items),
            )

        logger.info(
            "genericQuery %s finalizado — %d registro(s) em %d pagina(s)",
            table, len(all_items), page,
        )
        return all_items

    def count_records(self, table: str, where: Optional[str] = None, field: Optional[str] = None) -> int:
        """Conta registros de uma tabela usando genericQuery com pageSize=1.

        Args:
            table: Alias da tabela (SA1, SB1, etc.)
            where: Filtro WHERE opcional
            field: Campo a usar na query (obrigatorio para tabelas de dados)

        Returns:
            Total de registros
        """
        sx_upper = table.upper()
        if field:
            first_field = field
        elif sx_upper in SX_FIELD_MAP:
            first_field = SX_FIELD_MAP[sx_upper].split(",")[0]
        else:
            # Tabelas de dados precisam de um campo valido — usar R_E_C_N_O_ como ultimo recurso
            # Para resultados confiaveis, passe o parametro field com o primeiro campo do SX3
            first_field = "R_E_C_N_O_"

        params = {
            "tables": sx_upper,
            "fields": first_field,
            "pageSize": 1,
            "page": 1,
        }
        if where:
            params["where"] = where

        resp = self._get("/api/framework/v1/genericQuery", params=params)
        total = resp.get("total", 0)
        logger.info("count_records(%s) = %d", table, total)
        return total

    def query_sx_table(self, sx_name: str, page_size: int = 500) -> list[dict]:
        """Busca dados de uma tabela SX completa via genericQuery.

        Utiliza o mapeamento SX_FIELD_MAP para selecionar os campos corretos.

        Args:
            sx_name: Nome da tabela SX (SX2, SX3, SIX, etc.)
            page_size: Registros por pagina

        Returns:
            Lista de dicts com os dados brutos (transformacao no rest_ingestor)

        Raises:
            ValueError: Se sx_name nao esta mapeado em SX_FIELD_MAP
        """
        sx_upper = sx_name.upper()

        if sx_upper not in SX_FIELD_MAP:
            raise ValueError(
                f"Tabela '{sx_upper}' nao mapeada em SX_FIELD_MAP. "
                f"Tabelas disponiveis: {', '.join(sorted(SX_FIELD_MAP.keys()))}"
            )

        fields = SX_FIELD_MAP[sx_upper]
        logger.info("Buscando %s via genericQuery (campos: %s)...", sx_upper, fields)

        items = self.generic_query(
            table=sx_upper,
            fields=fields,
            page_size=page_size,
            max_pages=500,  # SX3 pode ter 200k+ campos, 500 pags x 500 = 250k registros
        )

        logger.info("%s retornou %d registro(s)", sx_upper, len(items))
        return items

    # ── Metodos internos ────────────────────────────────────────────────

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        """GET request com tratamento de erros.

        Args:
            path: Caminho relativo (ex: /api/framework/v1/Dictionary/Tables)
            params: Query parameters

        Returns:
            JSON de resposta parseado

        Raises:
            requests.exceptions.HTTPError: Em respostas 4xx/5xx
            requests.exceptions.ConnectionError: Falha de conexao
            requests.exceptions.Timeout: Timeout
        """
        url = f"{self.base_url}{path}"

        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            logger.error("Timeout ao acessar %s (%ds)", url, self.timeout)
            raise
        except requests.exceptions.ConnectionError as exc:
            logger.error("Erro de conexao com %s: %s", url, exc)
            raise
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            body = ""
            if exc.response is not None:
                body = exc.response.text[:300]
            logger.error("HTTP %s ao acessar %s: %s", status, url, body)
            raise
        except ValueError as exc:
            # JSON decode error
            logger.error("Resposta invalida (nao-JSON) de %s: %s", url, exc)
            raise

    def _paginate(
        self,
        path: str,
        params: Optional[dict] = None,
        max_pages: int = 100,
        page_size: int = 500,
    ) -> list[dict]:
        """Paginacao automatica para endpoints de dicionario.

        Args:
            path: Caminho da API
            params: Parametros extras (filtros, etc.)
            max_pages: Limite de paginas
            page_size: Registros por pagina

        Returns:
            Lista acumulada de items de todas as paginas
        """
        if params is None:
            params = {}

        params["pageSize"] = page_size
        params["page"] = 1

        all_items = []
        page = 1

        while page <= max_pages:
            params["page"] = page
            resp = self._get(path, params=params)

            items = resp.get("items", [])
            all_items.extend(items)

            has_next = resp.get("hasNext", False)
            if not has_next:
                break

            page += 1

            # Log a cada 5 paginas
            if page % 5 == 0:
                logger.info(
                    "Paginando %s — pagina %d, %d registros acumulados",
                    path, page, len(all_items),
                )

        if page > max_pages:
            logger.warning(
                "Paginacao de %s atingiu limite de %d paginas (%d registros). "
                "Pode haver dados faltando.",
                path, max_pages, len(all_items),
            )

        return all_items
