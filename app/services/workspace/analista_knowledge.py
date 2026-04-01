"""Knowledge base CRUD and seed for the Analista module — analista_diretrizes table."""
from app.services.workspace.workspace_db import Database


# ─────────────────────── CRUD ───────────────────────

def get_diretrizes(db: Database, tipo_demanda=None, categoria=None) -> list[dict]:
    """Busca diretrizes ativas.

    - tipo_demanda=None → retorna globais (tipo_demanda IS NULL) + do tipo informado.
    - categoria filtra adicionalmente quando fornecida.
    """
    params: list = []

    if tipo_demanda is None:
        where = "WHERE ativo = 1 AND tipo_demanda IS NULL"
    else:
        where = "WHERE ativo = 1 AND (tipo_demanda IS NULL OR tipo_demanda = ?)"
        params.append(tipo_demanda)

    if categoria is not None:
        where += " AND categoria = ?"
        params.append(categoria)

    sql = f"""
        SELECT id, tipo_demanda, categoria, titulo, conteudo, fonte, ativo, created_at
        FROM analista_diretrizes
        {where}
        ORDER BY categoria, id
    """
    rows = db.execute(sql, params).fetchall()
    cols = ["id", "tipo_demanda", "categoria", "titulo", "conteudo", "fonte", "ativo", "created_at"]
    return [dict(zip(cols, row)) for row in rows]


def add_diretriz(db: Database, tipo_demanda, categoria, titulo, conteudo, fonte="manual") -> int:
    """Insere nova diretriz. Retorna o id inserido."""
    db.execute(
        """INSERT INTO analista_diretrizes (tipo_demanda, categoria, titulo, conteudo, fonte)
           VALUES (?, ?, ?, ?, ?)""",
        [tipo_demanda, categoria, titulo, conteudo, fonte],
    )
    db.commit()
    row = db.execute("SELECT last_insert_rowid()").fetchone()
    return row[0]


def update_diretriz(db: Database, id: int, **kwargs) -> bool:
    """Atualiza campos da diretriz. Retorna True se algum registro foi atualizado."""
    allowed = {"tipo_demanda", "categoria", "titulo", "conteudo", "fonte", "ativo"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [id]
    db.execute(f"UPDATE analista_diretrizes SET {set_clause} WHERE id = ?", values)
    db.commit()
    changed = db.execute("SELECT changes()").fetchone()[0]
    return changed > 0


def deactivate_diretriz(db: Database, id: int) -> bool:
    """Desativa diretriz (ativo=0). Retorna True se algum registro foi alterado."""
    db.execute("UPDATE analista_diretrizes SET ativo = 0 WHERE id = ?", [id])
    db.commit()
    changed = db.execute("SELECT changes()").fetchone()[0]
    return changed > 0


def format_diretrizes_for_context(diretrizes: list[dict]) -> str:
    """Formata lista de diretrizes como texto para incluir em prompts."""
    if not diretrizes:
        return ""
    lines = ["## Diretrizes Aplicáveis\n"]
    for d in diretrizes:
        lines.append(f"### {d['titulo']}")
        lines.append(d['conteudo'])
        lines.append("")
    return "\n".join(lines)


# ─────────────────────── Seed ───────────────────────

_SEED_DIRETRIZES = [
    # ── MVC — global (tipo_demanda=None) ──
    dict(
        tipo_demanda=None,
        categoria="mvc",
        titulo="MVC — Estrutura básica",
        conteudo=(
            "Fontes MVC do Protheus usam funções padrão: ModelDef(), ViewModel(), ViewDef(). "
            "A função ModelDef define os campos e regras. ViewModel conecta model e view. "
            "Pontos de Entrada em MVC: antes/depois de cada operação CRUD."
        ),
        fonte="seed",
    ),
    dict(
        tipo_demanda=None,
        categoria="mvc",
        titulo="MVC — Validações no Model",
        conteudo=(
            "Validações em MVC devem ser feitas no ModelDef via regra de campo. "
            "User functions de validação devem seguir padrão U_NOME. "
            "Campos obrigatórios no MVC são definidos via oModel:SetRequiredMark()."
        ),
        fonte="seed",
    ),
    # ── Query — tipo_demanda=bug ──
    dict(
        tipo_demanda="bug",
        categoria="query",
        titulo="Query — RECNO em subquery",
        conteudo=(
            "Nunca use R_E_C_N_O_ em subqueries ou JOINs. "
            "Use sempre as chaves de negócio (ex: filial+código). "
            "RECNO pode mudar após reindexação."
        ),
        fonte="seed",
    ),
    dict(
        tipo_demanda="bug",
        categoria="query",
        titulo="Query — Alias obrigatório",
        conteudo=(
            "Todo campo em query SQL deve ter alias explícito quando há mais de uma tabela: "
            "SELECT SA1.A1_COD, SC5.C5_NUM... "
            "Sem alias, o DBAccess pode retornar colunas ambíguas."
        ),
        fonte="seed",
    ),
    dict(
        tipo_demanda="bug",
        categoria="query",
        titulo="Query — MSQuery e performance",
        conteudo=(
            "Evite MSQuery com LIKE '%termo%' (full scan). "
            "Prefira índices: SetOrder + SEEK ou SQL com índice. "
            "Para grandes volumes, use TCQUERY com LIMIT."
        ),
        fonte="seed",
    ),
    # ── SX3 — tipo_demanda=campo ──
    dict(
        tipo_demanda="campo",
        categoria="sx3",
        titulo="SX3 — Campos customizados",
        conteudo=(
            "Campos customizados SEMPRE devem ter Z no sufixo do nome (A1_ZCOD, não A1_COD). "
            "Prefixo padrão: primeiras 2 letras do alias da tabela. "
            "Tamanho máximo depende do banco (SQL Server: 8000 para C, Oracle: 4000)."
        ),
        fonte="seed",
    ),
    dict(
        tipo_demanda="campo",
        categoria="sx3",
        titulo="SX3 — Campo virtual vs real",
        conteudo=(
            "Campo virtual (X3_VIRTUAL=S) não existe fisicamente no banco. "
            "Não use virtual para campos obrigatórios nem para campos usados em índices. "
            "Campos virtuais têm inicializador obrigatório."
        ),
        fonte="seed",
    ),
    dict(
        tipo_demanda="campo",
        categoria="sx3",
        titulo="SX3 — Obrigatoriedade e ExecAutos",
        conteudo=(
            "Ao tornar um campo obrigatório, VERIFICAR todos os ExecAutos que gravam na tabela. "
            "Se o ExecAuto não preencher o campo, vai gerar erro em produção. "
            "Verificar também integrações WS/API."
        ),
        fonte="seed",
    ),
    # ── User Function — global (tipo_demanda=None) ──
    dict(
        tipo_demanda=None,
        categoria="user_function",
        titulo="User Function — Padrão de nomenclatura",
        conteudo=(
            "User functions customizadas DEVEM começar com U_ (U_VALCOD, U_CALCVAL). "
            "Sem U_, o Protheus não reconhece como user function externa. "
            "Ao referenciar em campo SX3, use sempre com U_."
        ),
        fonte="seed",
    ),
    dict(
        tipo_demanda=None,
        categoria="user_function",
        titulo="User Function — Declaração no fonte",
        conteudo=(
            "User Function deve ser declarada com 'User Function NOME()' no fonte. "
            "A função deve existir em algum fonte no diretório RPO. "
            "Se não existir, causa erro 'Function not found' em tempo de execução."
        ),
        fonte="seed",
    ),
    # ── PE — tipo_demanda=projeto ──
    dict(
        tipo_demanda="projeto",
        categoria="pe",
        titulo="PE — PARAMIXB e retorno",
        conteudo=(
            "Todo PE recebe parâmetros via PARAMIXB (array). "
            "Verificar a documentação do PE para saber o que cada posição contém. "
            "O retorno correto depende do PE: alguns retornam NIL, outros precisam retornar .T./.F. ou valor específico."
        ),
        fonte="seed",
    ),
    dict(
        tipo_demanda="projeto",
        categoria="pe",
        titulo="PE — Pontos de entrada comuns",
        conteudo=(
            "MT410BRW: navegação no pedido de venda. A410OK: confirma inclusão/alteração. "
            "MT410CAN: cancelamento. A410CPOS: após posicionamento. "
            "Para NF: MT100GRV (gravação NF saída), MT103GRV (NF entrada)."
        ),
        fonte="seed",
    ),
]


def seed_diretrizes(db: Database) -> int:
    """Popula a tabela com diretrizes iniciais se estiver vazia.

    Retorna número de diretrizes inseridas.
    """
    count_row = db.execute("SELECT COUNT(*) FROM analista_diretrizes").fetchone()
    if count_row and count_row[0] > 0:
        return 0

    for d in _SEED_DIRETRIZES:
        db.execute(
            """INSERT INTO analista_diretrizes (tipo_demanda, categoria, titulo, conteudo, fonte)
               VALUES (?, ?, ?, ?, ?)""",
            [d["tipo_demanda"], d["categoria"], d["titulo"], d["conteudo"], d["fonte"]],
        )
    db.commit()
    return len(_SEED_DIRETRIZES)
