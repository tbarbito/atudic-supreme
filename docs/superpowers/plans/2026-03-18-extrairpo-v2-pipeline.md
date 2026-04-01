# ExtraiRPO v2 — Pipeline de Documentacao Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separar geracao de docs do chat, criar pipeline dedicado com tela propria, ingerir processos padrao dinamicamente, simplificar chat para consulta.

**Architecture:** Pipeline de 3 etapas (Coletor puro -> Busca padrao -> 1 call LLM). Processos padrao ingeridos no ChromaDB automaticamente. Chat usa docs IA + padrao + TDN + dicionario cru como memoria. Frontend com nova tela "Gerar Docs".

**Tech Stack:** Python/FastAPI, Vue 3, ChromaDB, litellm, SQLite

---

## File Structure

### New Files
- `backend/services/doc_pipeline.py` — Pipeline de geracao: collect() + generate() + save()
- `backend/routers/generate.py` — Router da tela "Gerar Docs" (busca, gerar, status)
- `backend/services/padrao_ingestor.py` — Ingestao dinamica de processopadrao/*.md e TDN/
- `frontend/src/views/GerarDocsView.vue` — Tela de geracao de documentacao

### Modified Files
- `backend/app.py` — Incluir generate_router, endpoint de ingestao padrao
- `backend/routers/chat.py` — Remover geracao de docs, simplificar para consulta
- `backend/services/vectorstore.py` — Novas collections (padrao, tdn)
- `backend/services/knowledge.py` — Novo metodo collect_for_tables()
- `backend/services/llm.py` — Simplificar: remover 3 agentes, manter 1 call generate
- `frontend/src/App.vue` — Adicionar menu "Gerar Docs"
- `frontend/src/views/ClienteView.vue` — Pequenos ajustes

### Files to Keep (no changes)
- `backend/services/parser_sx.py` — Funciona bem
- `backend/services/parser_source.py` — Funciona bem
- `backend/services/database.py` — Schema OK
- `backend/services/config.py` — Config OK
- `backend/services/doc_generator.py` — save_doc/load_doc/list_docs OK

---

## Chunk 1: Ingestao de Processos Padrao

### Task 1: Criar padrao_ingestor.py

**Files:**
- Create: `backend/services/padrao_ingestor.py`

- [ ] **Step 1: Criar funcao que lista .md em processopadrao/**

```python
# backend/services/padrao_ingestor.py
from pathlib import Path

PADRAO_DIR = Path("processopadrao")

def list_padrao_docs() -> list[dict]:
    """Lista todos os .md disponiveis em processopadrao/"""
    docs = []
    if not PADRAO_DIR.exists():
        return docs
    for f in sorted(PADRAO_DIR.glob("*.md")):
        # Extrai modulo do nome: SIGAFAT_Fluxo_Faturamento.md -> sigafat
        parts = f.stem.split("_")
        modulo = parts[0].lower() if parts else f.stem.lower()
        docs.append({
            "arquivo": f.name,
            "modulo": modulo,
            "path": str(f),
            "size": f.stat().st_size,
        })
    return docs


def list_tdn_docs() -> list[dict]:
    """Lista docs TDN disponiveis."""
    tdn_dir = PADRAO_DIR / "TDN"
    docs = []
    if not tdn_dir.exists():
        return docs
    for f in sorted(tdn_dir.glob("*.md")):
        docs.append({
            "arquivo": f.name,
            "path": str(f),
            "size": f.stat().st_size,
        })
    return docs
```

- [ ] **Step 2: Criar funcao de chunking para markdown**

```python
def chunk_markdown(content: str, max_chars: int = 2000) -> list[str]:
    """Divide markdown em chunks por headers ## ou por tamanho."""
    sections = []
    current = ""
    for line in content.split("\n"):
        if line.startswith("## ") and current:
            sections.append(current.strip())
            current = line + "\n"
        else:
            current += line + "\n"
    if current.strip():
        sections.append(current.strip())

    # Sub-chunk sections that are too large
    chunks = []
    for section in sections:
        if len(section) <= max_chars:
            chunks.append(section)
        else:
            # Split by paragraphs
            for i in range(0, len(section), max_chars):
                chunks.append(section[i:i+max_chars])
    return chunks
```

- [ ] **Step 3: Criar funcao de ingestao no ChromaDB**

```python
def ingest_padrao(vs) -> dict:
    """Ingere todos os processos padrao no ChromaDB.

    Args:
        vs: VectorStore instance

    Returns:
        dict com contagem de docs e chunks ingeridos
    """
    vs.reset_collection("padrao")
    total_chunks = 0

    for doc in list_padrao_docs():
        content = Path(doc["path"]).read_text(encoding="utf-8")
        chunks = chunk_markdown(content)
        chunk_docs = []
        for i, chunk in enumerate(chunks):
            chunk_docs.append({
                "id": f"padrao_{doc['modulo']}_{i}",
                "content": chunk,
                "modulo": doc["modulo"],
                "arquivo": doc["arquivo"],
                "tipo": "processo_padrao",
            })
        vs.add_source_chunks("padrao", chunk_docs)
        total_chunks += len(chunk_docs)

    return {"docs": len(list_padrao_docs()), "chunks": total_chunks}


def ingest_tdn(vs) -> dict:
    """Ingere docs TDN markdown no ChromaDB."""
    vs.reset_collection("tdn")
    total_chunks = 0

    for doc in list_tdn_docs():
        content = Path(doc["path"]).read_text(encoding="utf-8")
        chunks = chunk_markdown(content, max_chars=3000)
        chunk_docs = []
        for i, chunk in enumerate(chunks):
            chunk_docs.append({
                "id": f"tdn_{doc['arquivo']}_{i}",
                "content": chunk,
                "arquivo": doc["arquivo"],
                "tipo": "tdn",
            })
        vs.add_source_chunks("tdn", chunk_docs)
        total_chunks += len(chunk_docs)

    return {"docs": len(list_tdn_docs()), "chunks": total_chunks}
```

- [ ] **Step 4: Commit**

```bash
git add backend/services/padrao_ingestor.py
git commit -m "feat: padrao_ingestor - dynamic ingestion of standard process docs and TDN"
```

### Task 2: Endpoint de ingestao padrao

**Files:**
- Modify: `backend/app.py`

- [ ] **Step 1: Adicionar endpoint POST /api/padrao/ingest**

```python
# Add to app.py
@app.post("/api/padrao/ingest")
async def ingest_padrao_endpoint():
    """Ingere processos padrao e TDN no ChromaDB."""
    import asyncio
    from backend.services.padrao_ingestor import ingest_padrao, ingest_tdn, list_padrao_docs
    from backend.services.vectorstore import VectorStore
    from backend.services.config import load_config, get_client_workspace

    config = load_config(CONFIG_PATH)
    if not config or not config.active_client:
        return {"error": "No active client"}

    client_dir = get_client_workspace(Path("workspace"), config.active_client)
    vs = VectorStore(client_dir / "db" / "chroma")
    vs.initialize()

    padrao_result = await asyncio.to_thread(ingest_padrao, vs)
    tdn_result = await asyncio.to_thread(ingest_tdn, vs)

    return {
        "padrao": padrao_result,
        "tdn": tdn_result,
    }

@app.get("/api/padrao/list")
async def list_padrao():
    from backend.services.padrao_ingestor import list_padrao_docs, list_tdn_docs
    return {
        "processos": list_padrao_docs(),
        "tdn": list_tdn_docs(),
    }
```

- [ ] **Step 2: Commit**

```bash
git add backend/app.py
git commit -m "feat: endpoints for standard process ingestion"
```

---

## Chunk 2: Pipeline de Geracao de Docs

### Task 3: Criar doc_pipeline.py — Coletor

**Files:**
- Create: `backend/services/doc_pipeline.py`

- [ ] **Step 1: Criar DocPipeline.collect()**

```python
# backend/services/doc_pipeline.py
"""Pipeline de geracao de documentacao tecnica.

Etapa 1 (collect): codigo puro, extrai dados do SQLite
Etapa 2 (generate): 1 call LLM com dados crus + doc padrao
Etapa 3 (save): salva docs + indexa no ChromaDB
"""
from pathlib import Path
from backend.services.database import Database
from backend.services.knowledge import KnowledgeService
from backend.services.vectorstore import VectorStore


class DocPipeline:
    def __init__(self, db: Database, vs: VectorStore, ks: KnowledgeService):
        self.db = db
        self.vs = vs
        self.ks = ks
        # Future: registered skills
        self._skills: dict = {}

    def collect(self, tables: list[str], fontes: list[str] = None) -> dict:
        """Etapa 1: Coleta dados crus do SQLite. Sem LLM.

        Args:
            tables: lista de codigos de tabela (ex: ["SA1", "SC5"])
            fontes: lista de arquivos fonte (ex: ["A020DELE.prw"])

        Returns:
            JSON estruturado com todos os dados relevantes
        """
        result = {
            "tabelas": [],
            "campos_custom": [],
            "campos_obrigatorios": [],
            "gatilhos": [],
            "indices": [],
            "relacionamentos": [],
            "parametros": [],
            "fontes": [],
        }

        for tab in tables:
            info = self.ks.get_table_info(tab)
            if not info:
                continue

            result["tabelas"].append({
                "codigo": tab,
                "nome": info.get("nome", ""),
                "total_campos": len(info.get("campos", [])),
                "total_custom": len(info.get("campos_custom", [])),
            })

            # Campos customizados com detalhes
            for c in info.get("campos_custom", []):
                result["campos_custom"].append({
                    "tabela": tab,
                    "campo": c.get("campo", ""),
                    "tipo": c.get("tipo", ""),
                    "tamanho": c.get("tamanho", ""),
                    "titulo": c.get("titulo", ""),
                    "descricao": c.get("descricao", ""),
                    "validacao": c.get("validacao", ""),
                    "inicializador": c.get("inicializador", ""),
                    "browse": c.get("browse", ""),
                })

            # Campos obrigatorios
            for c in info.get("campos", []):
                if c.get("obrigatorio"):
                    result["campos_obrigatorios"].append({
                        "tabela": tab,
                        "campo": c.get("campo", ""),
                        "tipo": c.get("tipo", ""),
                        "tamanho": c.get("tamanho", ""),
                        "titulo": c.get("titulo", ""),
                    })

            # Gatilhos
            for g in info.get("gatilhos", []):
                result["gatilhos"].append({
                    "tabela": tab,
                    "campo_origem": g.get("campo_origem", ""),
                    "campo_destino": g.get("campo_destino", ""),
                    "regra": g.get("regra", ""),
                    "tipo": g.get("tipo", ""),
                    "custom": g.get("custom", False),
                })

            # Indices
            for idx in info.get("indices", []):
                result["indices"].append({
                    "tabela": tab,
                    "indice": idx.get("indice", ""),
                    "chave": idx.get("chave", ""),
                    "descricao": idx.get("descricao", ""),
                })

        # Relacionamentos entre as tabelas selecionadas
        if tables:
            rels = self.ks.get_relacionamentos_for_tables(tables)
            result["relacionamentos"] = rels

        # Parametros MV_ relacionados
        params = self.db.execute(
            "SELECT variavel, tipo, descricao, conteudo, custom FROM parametros WHERE custom = 1"
        ).fetchall()
        for p in params:
            result["parametros"].append({
                "variavel": p[0], "tipo": p[1], "descricao": p[2],
                "valor": p[3], "custom": bool(p[4]),
            })

        # Fontes customizados
        if fontes:
            for nome in fontes:
                row = self.db.execute(
                    "SELECT arquivo, tipo, funcoes, pontos_entrada, tabelas_ref FROM fontes WHERE arquivo = ?",
                    (nome,)
                ).fetchone()
                if row:
                    result["fontes"].append({
                        "arquivo": row[0], "tipo": row[1],
                        "funcoes": row[2], "pontos_entrada": row[3],
                        "tabelas_ref": row[4],
                    })
        else:
            # Auto-detect: fontes that reference any of the selected tables
            for tab in tables:
                rows = self.db.execute(
                    "SELECT arquivo, tipo, funcoes, pontos_entrada, tabelas_ref FROM fontes WHERE tabelas_ref LIKE ?",
                    (f'%{tab}%',)
                ).fetchall()
                for row in rows:
                    if not any(f["arquivo"] == row[0] for f in result["fontes"]):
                        result["fontes"].append({
                            "arquivo": row[0], "tipo": row[1],
                            "funcoes": row[2], "pontos_entrada": row[3],
                            "tabelas_ref": row[4],
                        })

        # Source code chunks from vectorstore
        search_query = " ".join(tables)
        source_chunks = self.vs.search("fontes_custom", search_query, n_results=10)
        result["source_chunks"] = [
            {"arquivo": c["metadata"].get("arquivo", ""), "content": c["content"]}
            for c in source_chunks
        ]

        return result

    def search_padrao(self, tables: list[str], modulo: str = "") -> str:
        """Busca doc padrao relevante no ChromaDB."""
        query = modulo if modulo else " ".join(tables)
        results = self.vs.search("padrao", query, n_results=3)
        if not results:
            return ""
        return "\n\n".join([r["content"] for r in results])

    # ── Future: Skills ──

    def register_skill(self, name: str, skill_fn):
        """Registra skill especializada para uso futuro."""
        self._skills[name] = skill_fn

    def list_skills(self) -> list[str]:
        return list(self._skills.keys())
```

- [ ] **Step 2: Commit**

```bash
git add backend/services/doc_pipeline.py
git commit -m "feat: DocPipeline.collect() - structured data extraction from SQLite"
```

### Task 4: DocPipeline.generate() — 1 call LLM

**Files:**
- Modify: `backend/services/doc_pipeline.py`

- [ ] **Step 1: Adicionar prompt e metodo generate()**

```python
# Add to doc_pipeline.py

DOC_GENERATION_PROMPT = """Voce e um documentador tecnico de ambientes TOTVS Protheus.
Recebeu dados REAIS extraidos do dicionario de dados de um cliente.

REGRAS ABSOLUTAS:
- Documente APENAS o que esta nos dados fornecidos. NAO invente.
- NAO sugira melhorias, riscos, recomendacoes.
- NAO gere interfaces, telas ou mockups.
- Foco: documentar o estado atual do ambiente.

Com base nos dados, gere DOIS documentos como JSON:

1. "humano": Markdown tecnico com EXATAMENTE estas secoes:

   ## Visao Geral
   Resumo de 2-3 linhas do processo.

   ## Tabelas Envolvidas
   | Codigo | Nome | Campos | Customizados |

   ## Campos Customizados
   Para CADA campo custom:
   - **CAMPO** (Tipo, Tamanho) — Titulo
     - Descricao e finalidade
     - Validacao: `expressao` → explicacao em portugues
     - Inicializador: `expressao` → explicacao

   ## Campos Obrigatorios
   | Campo | Titulo | Tipo | Tamanho |

   ## Gatilhos
   Para CADA gatilho:
   - **Origem** → **Destino**
     - Regra: `expressao ADVPL`
     - Explicacao em portugues

   ## Indices
   | Indice | Chave | Descricao |

   ## Relacionamentos
   | Origem | Destino | Expressao |

   ## Parametros MV_ Customizados
   | Variavel | Tipo | Valor | Descricao |

   ## Fontes Customizados
   Para cada fonte: nome, tipo, quando executa, o que faz, tabelas que acessa

   ## Fluxo do Processo
   Passo a passo baseado nos dados acima.

   ## Comparacao com Padrao
   Se houver doc padrao, destacar: o que e padrao vs o que foi customizado.

2. "ia": Markdown com frontmatter YAML:
   ```yaml
   ---
   processo: slug
   tabelas: [lista]
   campos_custom: [{campo, tabela, titulo, finalidade}]
   gatilhos: [{origem, destino, regra}]
   fontes_custom: [lista]
   parametros: [{variavel, valor}]
   ---
   ```
   Seguido do mesmo conteudo tecnico.

Retorne APENAS JSON valido: {"humano": "...", "ia": "..."}"""


    def generate(self, collected_data: dict, slug: str, padrao_context: str = "",
                 llm=None) -> dict:
        """Etapa 2: 1 call LLM para gerar documentacao.

        Args:
            collected_data: output de collect()
            slug: identificador do documento
            padrao_context: doc padrao relevante (opcional)
            llm: LLMService instance

        Returns:
            {"humano": str, "ia": str}
        """
        import json as json_mod

        # Build context string from collected data
        context_parts = []
        context_parts.append(f"## Dados do Dicionario para: {slug}\n")
        context_parts.append(f"### Tabelas\n{json_mod.dumps(collected_data['tabelas'], ensure_ascii=False, indent=2)}\n")

        if collected_data["campos_custom"]:
            context_parts.append(f"### Campos Customizados ({len(collected_data['campos_custom'])} campos)\n")
            for c in collected_data["campos_custom"]:
                line = f"- **{c['campo']}** ({c['tipo']}, {c['tamanho']}) — {c['titulo']}"
                if c.get("descricao"):
                    line += f"\n  Descricao: {c['descricao']}"
                if c.get("validacao"):
                    line += f"\n  Validacao: `{c['validacao']}`"
                if c.get("inicializador"):
                    line += f"\n  Inicializador: `{c['inicializador']}`"
                context_parts.append(line)

        if collected_data["campos_obrigatorios"]:
            context_parts.append(f"\n### Campos Obrigatorios ({len(collected_data['campos_obrigatorios'])})")
            for c in collected_data["campos_obrigatorios"]:
                context_parts.append(f"- {c['campo']} | {c['titulo']} | {c['tipo']} | {c['tamanho']}")

        if collected_data["gatilhos"]:
            context_parts.append(f"\n### Gatilhos ({len(collected_data['gatilhos'])})")
            for g in collected_data["gatilhos"]:
                context_parts.append(f"- {g['campo_origem']} -> {g['campo_destino']} | Regra: {g['regra']} | Custom: {g['custom']}")

        if collected_data["indices"]:
            context_parts.append(f"\n### Indices ({len(collected_data['indices'])})")
            for idx in collected_data["indices"]:
                context_parts.append(f"- {idx['indice']} | {idx['chave']} | {idx['descricao']}")

        if collected_data["relacionamentos"]:
            context_parts.append(f"\n### Relacionamentos ({len(collected_data['relacionamentos'])})")
            for r in collected_data["relacionamentos"]:
                context_parts.append(f"- {r.get('tabela_origem','')} -> {r.get('tabela_destino','')} | {r.get('expressao_origem','')}")

        if collected_data["parametros"]:
            context_parts.append(f"\n### Parametros MV_ Customizados ({len(collected_data['parametros'])})")
            for p in collected_data["parametros"]:
                context_parts.append(f"- {p['variavel']} = {p['valor']} | {p['descricao']}")

        if collected_data["fontes"]:
            context_parts.append(f"\n### Fontes Customizados ({len(collected_data['fontes'])})")
            for f in collected_data["fontes"]:
                context_parts.append(f"- {f['arquivo']} (tipo: {f['tipo']})")
                if f.get("pontos_entrada"):
                    context_parts.append(f"  PEs: {f['pontos_entrada']}")

        if collected_data.get("source_chunks"):
            context_parts.append("\n### Codigo Fonte (trechos relevantes)")
            for sc in collected_data["source_chunks"][:5]:
                context_parts.append(f"#### {sc['arquivo']}\n```advpl\n{sc['content'][:1500]}\n```")

        context = "\n".join(context_parts)

        if padrao_context:
            context += f"\n\n## Referencia: Processo Padrao Protheus\n{padrao_context[:5000]}"

        # Truncate to stay within token limits
        if len(context) > 20000:
            context = context[:20000] + "\n\n[... dados truncados ...]"

        messages = [
            {"role": "system", "content": DOC_GENERATION_PROMPT},
            {"role": "user", "content": f"Gere documentacao tecnica para: {slug}\n\n{context}\n\nRetorne JSON com 'humano' e 'ia'."},
        ]

        result_text = llm._call(messages, temperature=0.3, use_gen=True)
        result_text = result_text.strip()
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[1].rsplit("```", 1)[0]

        return json_mod.loads(result_text)

    def save(self, knowledge_dir: Path, slug: str, docs: dict, modulo: str = ""):
        """Etapa 3: Salva docs e indexa no ChromaDB."""
        from backend.services.doc_generator import save_doc

        save_doc(knowledge_dir, slug, "humano", docs.get("humano", ""))
        save_doc(knowledge_dir, slug, "ia", docs.get("ia", ""))

        # Index in ChromaDB
        self.vs.delete_by_filter("knowledge_cliente", {"processo": slug})
        for camada in ["humano", "ia"]:
            content = docs.get(camada, "")
            if content:
                self.vs.add_source_chunks("knowledge_cliente", [{
                    "id": f"{slug}_{camada}",
                    "content": content,
                    "processo": slug,
                    "modulo": modulo or slug,
                }])

    def run(self, tables: list[str], fontes: list[str], slug: str,
            modulo: str, knowledge_dir: Path, llm=None) -> dict:
        """Executa pipeline completo: collect -> generate -> save."""
        collected = self.collect(tables, fontes)
        padrao = self.search_padrao(tables, modulo)
        docs = self.generate(collected, slug, padrao, llm)
        self.save(knowledge_dir, slug, docs, modulo)
        return {
            "slug": slug,
            "tables_analyzed": len(collected["tabelas"]),
            "custom_fields": len(collected["campos_custom"]),
            "triggers": len(collected["gatilhos"]),
            "sources": len(collected["fontes"]),
            "doc_humano_size": len(docs.get("humano", "")),
            "doc_ia_size": len(docs.get("ia", "")),
        }
```

- [ ] **Step 2: Commit**

```bash
git add backend/services/doc_pipeline.py
git commit -m "feat: DocPipeline.generate() + save() + run() - complete doc generation pipeline"
```

---

## Chunk 3: Router e Tela "Gerar Docs"

### Task 5: Criar generate router

**Files:**
- Create: `backend/routers/generate.py`

- [ ] **Step 1: Criar router com endpoints de busca e geracao**

```python
# backend/routers/generate.py
import json
import asyncio
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.services.config import load_config, get_client_workspace
from backend.services.database import Database
from backend.services.vectorstore import VectorStore
from backend.services.knowledge import KnowledgeService
from backend.services.llm import LLMService
from backend.services.doc_pipeline import DocPipeline

router = APIRouter(prefix="/api/generate", tags=["generate"])

WORKSPACE = Path("workspace")
CONFIG_PATH = Path("config.json")


def _get_pipeline():
    config = load_config(CONFIG_PATH)
    if not config or not config.active_client:
        raise HTTPException(400, "No active client")
    client_dir = get_client_workspace(WORKSPACE, config.active_client)
    db_path = client_dir / "db" / "extrairpo.db"
    if not db_path.exists():
        raise HTTPException(400, "Client not ingested")

    db = Database(db_path)
    db.initialize()
    vs = VectorStore(client_dir / "db" / "chroma")
    vs.initialize()
    ks = KnowledgeService(db)
    llm = LLMService(**config.llm)
    pipeline = DocPipeline(db, vs, ks)
    return pipeline, llm, client_dir, config


@router.get("/search")
async def search_tables_fontes(q: str = ""):
    """Busca tabelas e fontes por termo."""
    pipeline, llm, client_dir, config = _get_pipeline()
    results = {"tabelas": [], "fontes": []}

    if not q or len(q) < 2:
        return results

    q_upper = q.upper()
    q_lower = q.lower()

    # Search tables
    rows = pipeline.db.execute(
        "SELECT codigo, nome FROM tabelas WHERE codigo LIKE ? OR nome LIKE ? LIMIT 20",
        (f"%{q_upper}%", f"%{q_lower}%")
    ).fetchall()
    for r in rows:
        # Count custom fields
        custom_count = pipeline.db.execute(
            "SELECT COUNT(*) FROM campos WHERE tabela = ? AND custom = 1", (r[0],)
        ).fetchone()[0]
        results["tabelas"].append({
            "codigo": r[0], "nome": r[1], "campos_custom": custom_count,
        })

    # Search fontes
    rows = pipeline.db.execute(
        "SELECT arquivo, tipo, tabelas_ref FROM fontes WHERE arquivo LIKE ? LIMIT 20",
        (f"%{q_lower}%",)
    ).fetchall()
    for r in rows:
        results["fontes"].append({
            "arquivo": r[0], "tipo": r[1], "tabelas_ref": r[2],
        })

    return results


class GenerateRequest(BaseModel):
    tables: list[str]
    fontes: list[str] = []
    slug: str
    modulo: str = ""


@router.post("/run")
async def generate_doc(req: GenerateRequest):
    """Executa pipeline de geracao de doc."""
    pipeline, llm, client_dir, config = _get_pipeline()
    knowledge_dir = client_dir / "knowledge" / "cliente"

    try:
        result = await asyncio.to_thread(
            pipeline.run, req.tables, req.fontes, req.slug,
            req.modulo, knowledge_dir, llm
        )
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)[:500]}


@router.get("/summary")
async def environment_summary():
    """Resumo do ambiente: tabelas custom, fontes, etc."""
    pipeline, llm, client_dir, config = _get_pipeline()

    total_tables = pipeline.db.execute("SELECT COUNT(*) FROM tabelas").fetchone()[0]
    custom_fields = pipeline.db.execute("SELECT COUNT(*) FROM campos WHERE custom = 1").fetchone()[0]
    triggers = pipeline.db.execute("SELECT COUNT(*) FROM gatilhos").fetchone()[0]
    custom_triggers = pipeline.db.execute("SELECT COUNT(*) FROM gatilhos WHERE custom = 1").fetchone()[0]
    fontes = pipeline.db.execute("SELECT COUNT(*) FROM fontes").fetchone()[0]
    params = pipeline.db.execute("SELECT COUNT(*) FROM parametros WHERE custom = 1").fetchone()[0]

    # Tables with most custom fields
    top_tables = pipeline.db.execute("""
        SELECT c.tabela, t.nome, COUNT(*) as custom_count
        FROM campos c
        LEFT JOIN tabelas t ON c.tabela = t.codigo
        WHERE c.custom = 1
        GROUP BY c.tabela
        ORDER BY custom_count DESC
        LIMIT 15
    """).fetchall()

    return {
        "total_tables": total_tables,
        "custom_fields": custom_fields,
        "triggers": triggers,
        "custom_triggers": custom_triggers,
        "fontes": fontes,
        "custom_params": params,
        "top_tables": [
            {"codigo": r[0], "nome": r[1], "custom_count": r[2]}
            for r in top_tables
        ],
    }
```

- [ ] **Step 2: Registrar router no app.py**

```python
# Add to app.py imports:
from backend.routers.generate import router as generate_router

# Add after other includes:
app.include_router(generate_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/routers/generate.py backend/app.py
git commit -m "feat: generate router - search, run pipeline, environment summary"
```

### Task 6: Frontend — Tela GerarDocsView.vue

**Files:**
- Create: `frontend/src/views/GerarDocsView.vue`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Criar GerarDocsView.vue**

Tela com:
- Campo de busca (digita -> mostra tabelas/fontes)
- Checkboxes para selecionar tabelas e fontes
- Campo slug (auto-gerado baseado na selecao)
- Botao "Gerar Documento"
- Status: gerando... / sucesso / erro
- Resumo do ambiente (top tabelas customizadas)

- [ ] **Step 2: Adicionar menu no App.vue**

Adicionar "Gerar Docs" entre "Chat" e "Base Padrao" no sidebar.

- [ ] **Step 3: Build frontend**

```bash
cd frontend && npx vite build
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/GerarDocsView.vue frontend/src/App.vue frontend/dist/
git commit -m "feat: GerarDocsView - dedicated doc generation UI with search and status"
```

---

## Chunk 4: Simplificar Chat

### Task 7: Remover geracao de docs do chat

**Files:**
- Modify: `backend/routers/chat.py`

- [ ] **Step 1: Remover toda a secao de agent chain do event_generator**

Remover:
- Classificacao de `gerar_doc` e `slug`
- Bloco `if gerar_doc and slug:` inteiro (agentes, save_doc, etc)
- Import de doc_generator no chat
- `_call_with_retry`

Manter:
- Classificacao de `modulos`, `tabelas`, `search_terms` (para contexto)
- Busca no vectorstore
- Busca no dicionario
- System prompt
- Streaming response

- [ ] **Step 2: Adicionar busca em docs IA como fonte de contexto**

```python
# After existing context gathering, add:
# Search client knowledge docs (IA)
knowledge_results = vs.search("knowledge_cliente", search_query, n_results=3)
for r in knowledge_results:
    context_dicionario.append(f"## Doc Cliente: {r['metadata'].get('processo', '')}\n{r['content'][:3000]}")

# Search standard process docs
padrao_results = vs.search("padrao", search_query, n_results=2)
for r in padrao_results:
    context_dicionario.append(f"## Processo Padrao:\n{r['content'][:2000]}")
```

- [ ] **Step 3: Remover doc_updated do chat_history**

O campo `doc_updated` no INSERT nao precisa mais ser populado (sempre None).

- [ ] **Step 4: Commit**

```bash
git add backend/routers/chat.py
git commit -m "refactor: simplify chat - remove doc generation, add knowledge search"
```

### Task 8: Frontend — Remover badge doc_updated do chat

**Files:**
- Modify: `frontend/src/views/ChatView.vue`

- [ ] **Step 1: Remover badge verde "Doc atualizado" e agent_status handling**

- [ ] **Step 2: Build frontend**

```bash
cd frontend && npx vite build
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/ChatView.vue frontend/dist/
git commit -m "refactor: remove doc generation UI from chat"
```

---

## Chunk 5: Integracao e Polish

### Task 9: Auto-ingestao de padrao no setup

**Files:**
- Modify: `backend/routers/setup.py`

- [ ] **Step 1: Apos ingestion do cliente, auto-ingerir processos padrao**

No final da Fase 2 (depois de indexar fontes), chamar `ingest_padrao(vs)` e `ingest_tdn(vs)`.

- [ ] **Step 2: Commit**

```bash
git add backend/routers/setup.py
git commit -m "feat: auto-ingest standard processes after client setup"
```

### Task 10: Remover 3 agentes do llm.py

**Files:**
- Modify: `backend/services/llm.py`

- [ ] **Step 1: Remover metodos run_agent_dicionarista, run_agent_analista_fontes, run_agent_documentador**

Esses metodos nao sao mais usados. O pipeline usa `_call()` diretamente.

Manter:
- `_call()` (usado pelo pipeline)
- `chat_stream()` (usado pelo chat)
- `classify()` (usado pelo chat)
- Prompts CLASSIFY_PROMPT (usado pelo chat)
- DOC_GENERATION_PROMPT movido pro doc_pipeline.py

Remover:
- AGENT_DICIONARISTA, AGENT_ANALISTA_FONTES, AGENT_DOCUMENTADOR
- run_agent_dicionarista(), run_agent_analista_fontes(), run_agent_documentador()

- [ ] **Step 2: Commit**

```bash
git add backend/services/llm.py
git commit -m "refactor: remove 3-agent chain from LLM, pipeline handles generation"
```

### Task 11: Teste end-to-end

- [ ] **Step 1: Iniciar servidor**

```bash
cd d:/IA/Projetos/Protheus
.venv/Scripts/python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8032
```

- [ ] **Step 2: Testar ingestao padrao**

```bash
curl -X POST http://127.0.0.1:8032/api/padrao/ingest
```

Expected: `{"padrao": {"docs": 3, "chunks": N}, "tdn": {"docs": 3, "chunks": N}}`

- [ ] **Step 3: Testar busca**

```bash
curl "http://127.0.0.1:8032/api/generate/search?q=cliente"
```

Expected: Lista de tabelas (SA1, SA2...) e fontes com "cliente" no nome

- [ ] **Step 4: Testar geracao de doc**

```bash
curl -X POST http://127.0.0.1:8032/api/generate/run \
  -H "Content-Type: application/json" \
  -d '{"tables": ["SA1"], "slug": "cadastro-cliente-marfrig", "modulo": "faturamento"}'
```

Expected: `{"status": "ok", "slug": "cadastro-cliente-marfrig", ...}`

- [ ] **Step 5: Verificar doc salvo**

```bash
ls workspace/clients/marfrig/knowledge/cliente/humano/
cat workspace/clients/marfrig/knowledge/cliente/humano/cadastro-cliente-marfrig.md | head -30
```

- [ ] **Step 6: Testar chat (sem geracao)**

Enviar mensagem no chat e verificar que:
- Responde com base nos docs IA + padrao + dicionario
- NAO tenta gerar doc
- Navegacao entre menus funciona sem travar

- [ ] **Step 7: Commit final**

```bash
git add -A
git commit -m "feat: ExtraiRPO v2 - dedicated doc pipeline, simplified chat, standard process ingestion"
```

---

## Resumo de Dependencias

```
Task 1 (padrao_ingestor) ──┐
Task 2 (endpoint)          ├── independentes
Task 3 (collect)           │
                           ↓
Task 4 (generate) ←── depende de Task 3
Task 5 (router)   ←── depende de Task 3 + 4
Task 6 (frontend) ←── depende de Task 5
Task 7 (chat)     ←── independente
Task 8 (chat UI)  ←── depende de Task 7
Task 9 (auto-ingest) ←── depende de Task 1
Task 10 (cleanup) ←── depende de Task 7
Task 11 (e2e)     ←── depende de TUDO
```

Tasks 1, 2, 3, 7 podem rodar em paralelo.
