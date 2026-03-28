"""
Serviço de Memória Persistente do Agente Inteligente do AtuDIC.

Gerencia 3 camadas de memória (semântica, episódica, procedural) com
armazenamento em arquivos Markdown e indexação FTS5 no SQLite para
busca BM25 de alta performance.

Arquitetura:
- Fonte da verdade: arquivos .md em memory/
- Índice de busca: SQLite com FTS5 (memory.db)
- Config do agente: PostgreSQL (agent_settings)
"""

import os
import re
import sqlite3
import hashlib
import logging
import threading
from collections import OrderedDict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# =====================================================================
# CACHE DE QUERY EMBEDDINGS — evita chamadas repetidas de embedding
# Mesma query (ou query identica recente) reutiliza o vetor em memoria.
# LRU com limite de 200 entradas (~1.6 MB para 1024d vectors).
# =====================================================================
_QUERY_EMBED_CACHE_MAX = 200
_query_embed_cache = OrderedDict()
_query_embed_cache_lock = threading.Lock()
_embed_token_counter = {"calls": 0, "cached": 0, "chars_sent": 0}


def _cache_get(query_hash):
    """Busca embedding no cache LRU."""
    with _query_embed_cache_lock:
        if query_hash in _query_embed_cache:
            _query_embed_cache.move_to_end(query_hash)
            _embed_token_counter["cached"] += 1
            return _query_embed_cache[query_hash]
    return None


def _cache_put(query_hash, embedding):
    """Armazena embedding no cache LRU."""
    with _query_embed_cache_lock:
        _query_embed_cache[query_hash] = embedding
        if len(_query_embed_cache) > _QUERY_EMBED_CACHE_MAX:
            _query_embed_cache.popitem(last=False)


def get_embedding_stats():
    """Retorna estatisticas de uso de embeddings (para monitoramento de custo)."""
    return dict(_embed_token_counter)

# Diretório padrão da memória
# No modo PyInstaller (frozen), os .md seed ficam em _MEIPASS/memory/
# mas o DB e logs devem ficar no diretório de trabalho (gravável)
import sys as _sys
if getattr(_sys, "frozen", False):
    # Executável PyInstaller: diretório do .exe
    _DEFAULT_MEMORY_DIR = os.path.join(os.path.dirname(_sys.executable), "memory")
    _SEED_DIR = os.path.join(_sys._MEIPASS, "memory")
else:
    _DEFAULT_MEMORY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "memory")
    _SEED_DIR = _DEFAULT_MEMORY_DIR

# Tamanho máximo de chunk (caracteres) — seções maiores são subdivididas
CHUNK_MAX_SIZE = 3000
CHUNK_OVERLAP = 200


class AgentMemoryService:
    """Serviço de memória persistente do agente inteligente."""

    def __init__(self, memory_dir=None):
        self.memory_dir = memory_dir or _DEFAULT_MEMORY_DIR
        self.db_path = os.path.join(self.memory_dir, "memory.db")
        self._conn = None

        # Garantir que as pastas existem
        os.makedirs(os.path.join(self.memory_dir, "logs"), exist_ok=True)
        os.makedirs(os.path.join(self.memory_dir, "sessions"), exist_ok=True)

        # No modo PyInstaller, copiar seeds da pasta embarcada se não existirem
        if _SEED_DIR != self.memory_dir:
            import shutil
            for seed_file in ("MEMORY.md", "TOOLS.md"):
                dest = os.path.join(self.memory_dir, seed_file)
                src = os.path.join(_SEED_DIR, seed_file)
                if not os.path.exists(dest) and os.path.exists(src):
                    shutil.copy2(src, dest)
                    logger.info("📋 Seed copiado: %s", seed_file)

        # Inicializar banco
        self.init_db()

    # =================================================================
    # GESTÃO DO SQLITE
    # =================================================================

    def _get_conn(self):
        """Retorna conexão SQLite (cria se não existe)."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            # WAL mode para concorrência
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    def init_db(self):
        """Cria schema SQLite com FTS5 se não existe."""
        conn = self._get_conn()
        cursor = conn.cursor()

        # Tabela principal de chunks
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks_meta (
                chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file TEXT NOT NULL,
                chunk_type TEXT NOT NULL,
                section_title TEXT,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                char_start INTEGER,
                char_end INTEGER,
                environment_id INTEGER,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(content_hash, source_file)
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_type ON chunks_meta(chunk_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks_meta(source_file)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chunks_env ON chunks_meta(environment_id)")

        # Coluna embedding (adicionada em 19D — busca híbrida)
        try:
            cursor.execute("ALTER TABLE chunks_meta ADD COLUMN embedding TEXT")
        except sqlite3.OperationalError:
            pass  # Coluna já existe

        # FTS5 para busca BM25
        # tokenize unicode61 com remove_diacritics 2: "faturacao" == "faturação"
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                content,
                source_file,
                chunk_type,
                section_title,
                content='chunks_meta',
                content_rowid='chunk_id',
                tokenize='unicode61 remove_diacritics 2'
            )
        """)

        # Triggers para sincronizar FTS5 com chunks_meta
        cursor.executescript("""
            CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks_meta BEGIN
                INSERT INTO chunks_fts(rowid, content, source_file, chunk_type, section_title)
                VALUES (new.chunk_id, new.content, new.source_file, new.chunk_type, new.section_title);
            END;

            CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks_meta BEGIN
                INSERT INTO chunks_fts(chunks_fts, rowid, content, source_file, chunk_type, section_title)
                VALUES ('delete', old.chunk_id, old.content, old.source_file, old.chunk_type, old.section_title);
            END;

            CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks_meta BEGIN
                INSERT INTO chunks_fts(chunks_fts, rowid, content, source_file, chunk_type, section_title)
                VALUES ('delete', old.chunk_id, old.content, old.source_file, old.chunk_type, old.section_title);
                INSERT INTO chunks_fts(rowid, content, source_file, chunk_type, section_title)
                VALUES (new.chunk_id, new.content, new.source_file, new.chunk_type, new.section_title);
            END;
        """)

        # Sessões do agente
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_sessions (
                session_id TEXT PRIMARY KEY,
                environment_id INTEGER,
                started_at TEXT DEFAULT (datetime('now')),
                ended_at TEXT,
                summary TEXT,
                chunks_accessed INTEGER DEFAULT 0,
                queries_made INTEGER DEFAULT 0
            )
        """)

        # Log de buscas (para refinar relevância futuramente)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS search_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                results_count INTEGER,
                top_chunk_id INTEGER,
                session_id TEXT,
                searched_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # Mensagens do chat (Item 9B)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                environment_id INTEGER,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                intent TEXT,
                confidence REAL,
                response_data TEXT,
                sources_consulted TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (session_id) REFERENCES agent_sessions(session_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_messages(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chat_env ON chat_messages(environment_id)")

        # Dicionário SX2 do Protheus (tabelas padrão)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sx2_tables (
                alias TEXT PRIMARY KEY,
                description_pt TEXT NOT NULL,
                description_en TEXT,
                prefix TEXT
            )
        """)

        # Feedback do usuário (20C)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER,
                session_id TEXT,
                environment_id INTEGER,
                rating INTEGER NOT NULL,
                intent TEXT,
                specialist TEXT,
                skills_used TEXT,
                tools_used TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_intent ON agent_feedback(intent)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_date ON agent_feedback(created_at)")

        conn.commit()
        logger.info("🧠 Agent memory DB inicializado: %s", self.db_path)

    def close(self):
        """Fecha conexão SQLite."""
        if self._conn:
            self._conn.close()
            self._conn = None

    # =================================================================
    # INGESTÃO DE MARKDOWN
    # =================================================================

    def _hash_content(self, text):
        """Gera SHA256 do conteúdo para deduplicação."""
        return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

    def _parse_markdown_sections(self, content):
        """Quebra Markdown em seções por headings (## ou ###).

        Retorna lista de dicts: [{title, content, char_start, char_end}]
        """
        sections = []
        # Regex para headings de nível 2 ou 3
        pattern = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)
        matches = list(pattern.finditer(content))

        if not matches:
            # Arquivo sem headings — trata como chunk único
            text = content.strip()
            if text:
                sections.append({
                    "title": "(sem título)",
                    "content": text,
                    "char_start": 0,
                    "char_end": len(content)
                })
            return sections

        # Texto antes do primeiro heading (preâmbulo)
        if matches[0].start() > 0:
            preamble = content[:matches[0].start()].strip()
            if preamble and len(preamble) > 50:
                sections.append({
                    "title": "(preâmbulo)",
                    "content": preamble,
                    "char_start": 0,
                    "char_end": matches[0].start()
                })

        # Cada heading até o próximo heading
        for i, match in enumerate(matches):
            title = match.group(2).strip()
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            text = content[start:end].strip()

            if text:
                sections.append({
                    "title": title,
                    "content": text,
                    "char_start": start,
                    "char_end": end
                })

        return sections

    def _split_large_chunk(self, section):
        """Subdivide seção grande em chunks menores com overlap."""
        text = section["content"]
        if len(text) <= CHUNK_MAX_SIZE:
            return [section]

        chunks = []
        start = 0
        while start < len(text):
            end = min(start + CHUNK_MAX_SIZE, len(text))

            # Tentar quebrar em linha vazia mais próxima
            if end < len(text):
                break_pos = text.rfind("\n\n", start + CHUNK_MAX_SIZE // 2, end)
                if break_pos > start:
                    end = break_pos

            chunk_text = text[start:end].strip()
            if chunk_text:
                part = len(chunks) + 1
                chunks.append({
                    "title": f"{section['title']} (parte {part})",
                    "content": chunk_text,
                    "char_start": section["char_start"] + start,
                    "char_end": section["char_start"] + end
                })

            start = max(start + 1, end - CHUNK_OVERLAP)

        return chunks

    def ingest_file(self, filepath, chunk_type, environment_id=None):
        """Ingere um arquivo .md na memória — parse + indexação FTS5.

        Args:
            filepath: caminho relativo dentro de memory/ (ex: 'MEMORY.md')
            chunk_type: 'semantic', 'episodic', 'procedural'
            environment_id: id do ambiente (None = global)

        Returns:
            int: número de chunks inseridos/atualizados
        """
        full_path = os.path.join(self.memory_dir, filepath)
        if not os.path.isfile(full_path):
            logger.warning("Arquivo não encontrado para ingestão: %s", full_path)
            return 0

        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        if not content.strip():
            return 0

        sections = self._parse_markdown_sections(content)

        # Subdividir seções grandes
        all_chunks = []
        for section in sections:
            all_chunks.extend(self._split_large_chunk(section))

        conn = self._get_conn()
        cursor = conn.cursor()
        inserted = 0

        for chunk in all_chunks:
            content_hash = self._hash_content(chunk["content"])

            # Upsert: se hash+source já existe, pular (conteúdo idêntico)
            cursor.execute(
                "SELECT chunk_id FROM chunks_meta WHERE content_hash = ? AND source_file = ?",
                (content_hash, filepath)
            )
            existing = cursor.fetchone()

            if existing:
                continue

            cursor.execute("""
                INSERT INTO chunks_meta
                (source_file, chunk_type, section_title, content, content_hash,
                 char_start, char_end, environment_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                filepath, chunk_type, chunk["title"], chunk["content"],
                content_hash, chunk["char_start"], chunk["char_end"],
                environment_id
            ))
            inserted += 1

        conn.commit()
        logger.info("📥 Ingestão de %s: %d chunks inseridos (total seções: %d)",
                     filepath, inserted, len(all_chunks))
        return inserted

    def ingest_all(self, environment_id=None, llm_provider=None):
        """Ingere todos os arquivos de memória e gera embeddings se provider disponivel.

        Args:
            environment_id: ID do ambiente (opcional)
            llm_provider: provider LLM para gerar embeddings (opcional)

        Returns:
            dict: {arquivo: chunks_inseridos, _embeddings_generated: N}
        """
        results = {}

        # Memória semântica
        if os.path.isfile(os.path.join(self.memory_dir, "MEMORY.md")):
            results["MEMORY.md"] = self.ingest_file("MEMORY.md", "semantic", environment_id)

        # Memória procedural
        if os.path.isfile(os.path.join(self.memory_dir, "TOOLS.md")):
            results["TOOLS.md"] = self.ingest_file("TOOLS.md", "procedural", environment_id)

        # Base de conhecimento TDN Protheus (somente tdn_*.md < 2MB)
        # Arquivos maiores vao pro PostgreSQL (tsvector) — ver tdn_ingestor.py
        _MAX_SQLITE_FILE_SIZE = 2 * 1024 * 1024  # 2MB
        for filename in sorted(os.listdir(self.memory_dir)):
            if filename.startswith("tdn_") and filename.endswith(".md"):
                filepath = os.path.join(self.memory_dir, filename)
                filesize = os.path.getsize(filepath)
                if filesize <= _MAX_SQLITE_FILE_SIZE:
                    results[filename] = self.ingest_file(filename, "semantic", environment_id)
                else:
                    logger.info("⏭️ %s (%d MB) → PostgreSQL (acima do limite SQLite)",
                                filename, filesize // (1024 * 1024))

        # Memória episódica (logs diários)
        logs_dir = os.path.join(self.memory_dir, "logs")
        if os.path.isdir(logs_dir):
            for filename in sorted(os.listdir(logs_dir)):
                if filename.endswith(".md"):
                    rel_path = os.path.join("logs", filename)
                    results[rel_path] = self.ingest_file(rel_path, "episodic", environment_id)

        total = sum(results.values())
        logger.info("📥 Ingestão completa: %d chunks totais em %d arquivos", total, len(results))

        # Gerar embeddings automaticamente se provider disponivel
        if llm_provider and getattr(llm_provider, "supports_embedding", False):
            embedded = self.embed_all_chunks(llm_provider)
            results["_embeddings_generated"] = embedded
            logger.info("📐 Embeddings gerados automaticamente: %d chunks", embedded)

        return results

    # =================================================================
    # BUSCA BM25 (FTS5)
    # =================================================================

    def search_bm25(self, query, chunk_type=None, environment_id=None, limit=10):
        """Busca textual BM25 via FTS5.

        Args:
            query: texto de busca (suporta operadores FTS5: AND, OR, NOT, "frase exata")
            chunk_type: filtrar por tipo ('semantic', 'episodic', 'procedural')
            environment_id: filtrar por ambiente (None = todos)
            limit: máximo de resultados

        Returns:
            list[dict]: resultados ordenados por relevância (rank)
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        # Escapar caracteres especiais do FTS5 que podem causar erro
        safe_query = self._sanitize_fts_query(query)
        if not safe_query:
            return []

        # Construir query com filtros
        sql = """
            SELECT
                m.chunk_id, m.source_file, m.chunk_type, m.section_title,
                m.content, m.environment_id, m.created_at,
                rank
            FROM chunks_fts f
            JOIN chunks_meta m ON f.rowid = m.chunk_id
            WHERE chunks_fts MATCH ?
        """
        params = [safe_query]

        if chunk_type:
            sql += " AND m.chunk_type = ?"
            params.append(chunk_type)

        if environment_id is not None:
            sql += " AND (m.environment_id IS NULL OR m.environment_id = ?)"
            params.append(environment_id)

        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        try:
            cursor.execute(sql, params)
            results = [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError as e:
            logger.warning("Erro na busca FTS5: %s (query: %s)", e, safe_query)
            results = []

        # Registrar busca no log
        top_id = results[0]["chunk_id"] if results else None
        cursor.execute(
            "INSERT INTO search_log (query, results_count, top_chunk_id) VALUES (?, ?, ?)",
            (query, len(results), top_id)
        )
        conn.commit()

        return results

    def search_hybrid(self, query, llm_provider=None, chunk_type=None, environment_id=None, limit=10):
        """Busca híbrida: BM25 + embedding similarity (RRF merge).

        Se llm_provider suporta embeddings, combina os resultados do BM25
        com busca vetorial via cosine similarity. Caso contrário, faz
        fallback para BM25 puro.

        Args:
            query: texto de busca
            llm_provider: provider LLM (para gerar embedding da query)
            chunk_type: filtrar por tipo
            environment_id: filtrar por ambiente
            limit: máximo de resultados

        Returns:
            list[dict]: resultados rankeados por RRF (BM25 + embedding)
        """
        # 1. Busca BM25 (sempre disponível)
        bm25_results = self.search_bm25(query, chunk_type=chunk_type, environment_id=environment_id, limit=limit * 2)

        # 2. Tentar busca vetorial (com cache para economizar tokens)
        if llm_provider and getattr(llm_provider, "supports_embedding", False):
            query_hash = hashlib.md5(query.strip().lower().encode()).hexdigest()
            query_embedding = _cache_get(query_hash)

            if query_embedding is None:
                # Cache miss — chamar API de embedding
                query_embedding = llm_provider.get_embedding(query)
                if query_embedding:
                    _cache_put(query_hash, query_embedding)
                    _embed_token_counter["calls"] += 1
                    _embed_token_counter["chars_sent"] += len(query)

            if query_embedding:
                embed_results = self._search_by_embedding(
                    query_embedding, chunk_type=chunk_type, environment_id=environment_id, limit=limit * 2
                )

                if embed_results:
                    # 3. Merge via Reciprocal Rank Fusion (RRF)
                    merged = self._rrf_merge(bm25_results, embed_results, limit=limit)
                    logger.info(
                        "🔍 Busca híbrida: BM25=%d + Embedding=%d → merged=%d",
                        len(bm25_results), len(embed_results), len(merged),
                    )
                    return merged

        # Fallback: BM25 puro
        return bm25_results[:limit]

    def _search_by_embedding(self, query_embedding, chunk_type=None, environment_id=None, limit=20):
        """Busca por similaridade vetorial (cosine similarity).

        Compara o embedding da query contra os embeddings armazenados
        nos chunks. Usa linear scan (eficiente para < 5000 chunks).
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        # Buscar chunks com embeddings
        sql = """
            SELECT m.chunk_id, m.source_file, m.chunk_type, m.section_title,
                   m.content, m.environment_id, m.created_at, m.embedding
            FROM chunks_meta m
            WHERE m.embedding IS NOT NULL
        """
        params = []

        if chunk_type:
            sql += " AND m.chunk_type = ?"
            params.append(chunk_type)

        if environment_id is not None:
            sql += " AND (m.environment_id IS NULL OR m.environment_id = ?)"
            params.append(environment_id)

        try:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        except Exception:
            return []

        if not rows:
            return []

        # Calcular cosine similarity para cada chunk
        import json as _json

        scored = []
        for row in rows:
            row_dict = dict(row)
            try:
                chunk_embedding = _json.loads(row_dict["embedding"])
                similarity = self._cosine_similarity(query_embedding, chunk_embedding)
                row_dict["similarity"] = similarity
                row_dict.pop("embedding", None)  # Não retornar o vetor
                scored.append(row_dict)
            except (ValueError, TypeError, _json.JSONDecodeError):
                continue

        # Ordenar por similaridade (maior primeiro)
        scored.sort(key=lambda x: x.get("similarity", 0), reverse=True)
        return scored[:limit]

    @staticmethod
    def _cosine_similarity(vec_a, vec_b):
        """Cosine similarity entre dois vetores (sem numpy)."""
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0

        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = sum(a * a for a in vec_a) ** 0.5
        norm_b = sum(b * b for b in vec_b) ** 0.5

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot / (norm_a * norm_b)

    @staticmethod
    def _rrf_merge(bm25_results, embed_results, limit=10, k=60):
        """Reciprocal Rank Fusion — combina dois rankings.

        RRF score = sum(1 / (k + rank)) para cada lista.
        k=60 é o default do paper original (Cormack et al. 2009).
        """
        scores = {}
        seen = {}

        # BM25 ranks
        for rank, r in enumerate(bm25_results):
            cid = r["chunk_id"]
            scores[cid] = scores.get(cid, 0) + 1.0 / (k + rank + 1)
            seen[cid] = r

        # Embedding ranks
        for rank, r in enumerate(embed_results):
            cid = r["chunk_id"]
            scores[cid] = scores.get(cid, 0) + 1.0 / (k + rank + 1)
            if cid not in seen:
                seen[cid] = r

        # Ordenar por RRF score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        results = []
        for cid, rrf_score in ranked[:limit]:
            item = dict(seen[cid])
            item["rrf_score"] = round(rrf_score, 4)
            results.append(item)

        return results

    def embed_chunk(self, chunk_id, content, llm_provider):
        """Gera e salva embedding para um chunk específico."""
        if not llm_provider or not getattr(llm_provider, "supports_embedding", False):
            return False

        embedding = llm_provider.get_embedding(content)
        if not embedding:
            return False

        import json as _json

        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE chunks_meta SET embedding = ? WHERE chunk_id = ?",
                (_json.dumps(embedding), chunk_id),
            )
            conn.commit()
            return True
        except Exception as e:
            logger.warning("Erro ao salvar embedding chunk %d: %s", chunk_id, e)
            return False

    def embed_all_chunks(self, llm_provider, batch_size=20):
        """Gera embeddings para todos os chunks que ainda nao tem.

        Usa batch embedding quando o provider suporta (OpenAI, Mistral, etc)
        para reduzir chamadas de API e economizar tokens de overhead.

        Args:
            llm_provider: provider com suporte a embedding
            batch_size: textos por chamada batch (default 20)
        """
        if not llm_provider or not getattr(llm_provider, "supports_embedding", False):
            logger.info("Provider nao suporta embeddings, pulando")
            return 0

        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT chunk_id, content FROM chunks_meta WHERE embedding IS NULL")
        rows = cursor.fetchall()

        if not rows:
            return 0

        import json as _json
        count = 0
        has_batch = hasattr(llm_provider, "get_embeddings_batch")

        # Processar em lotes
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            texts = [row["content"] for row in batch]
            ids = [row["chunk_id"] for row in batch]

            if has_batch and len(texts) > 1:
                # Batch: 1 chamada API para N textos
                embeddings = llm_provider.get_embeddings_batch(texts)
            else:
                # Individual: N chamadas
                embeddings = [llm_provider.get_embedding(t) for t in texts]

            for chunk_id, embedding in zip(ids, embeddings):
                if embedding:
                    try:
                        cursor.execute(
                            "UPDATE chunks_meta SET embedding = ? WHERE chunk_id = ?",
                            (_json.dumps(embedding), chunk_id),
                        )
                        count += 1
                    except Exception as e:
                        logger.warning("Erro ao salvar embedding chunk %d: %s", chunk_id, e)

            conn.commit()
            _embed_token_counter["calls"] += 1 if has_batch else len(texts)
            _embed_token_counter["chars_sent"] += sum(len(t) for t in texts)

        logger.info("📐 Embeddings gerados: %d/%d chunks (batch_size=%d)", count, len(rows), batch_size)
        return count

    def _sanitize_fts_query(self, query):
        """Sanitiza query para FTS5 — remove operadores inválidos."""
        if not query or not query.strip():
            return None

        # Substituir hífens por espaço (hífen é operador NOT no FTS5)
        # Ex: "ORA-01017" → "ORA 01017"
        sanitized = query.replace("-", " ")

        # Remover caracteres que causam erro no FTS5
        # Manter: letras, números, espaços, aspas, _
        # NOTA: ponto (.) e operadores FTS5 — devem ser removidos
        sanitized = re.sub(r'[^\w\s"_]', ' ', sanitized, flags=re.UNICODE)
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()

        if not sanitized:
            return None

        return sanitized

    def search_by_section(self, section_title, limit=20):
        """Busca chunks por título de seção (match parcial)."""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT chunk_id, source_file, chunk_type, section_title, content,
                   environment_id, created_at
            FROM chunks_meta
            WHERE section_title LIKE ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (f"%{section_title}%", limit))

        return [dict(row) for row in cursor.fetchall()]

    # =================================================================
    # CRUD DE MEMÓRIA
    # =================================================================

    def add_semantic_entry(self, section, content, environment_id=None):
        """Adiciona entrada na memória semântica (MEMORY.md).

        Appenda uma nova seção no arquivo e re-ingere.
        """
        return self._append_to_file("MEMORY.md", section, content, "semantic", environment_id)

    def add_episodic_entry(self, content, environment_id=None):
        """Adiciona entrada na memória episódica (log do dia).

        Cria/appenda no arquivo logs/YYYY-MM-DD.md
        """
        today = datetime.now().strftime("%Y-%m-%d")
        filename = os.path.join("logs", f"{today}.md")
        full_path = os.path.join(self.memory_dir, filename)

        # Se arquivo não existe, criar com header
        if not os.path.isfile(full_path):
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(f"# Log do Agente — {today}\n\n")

        # Adicionar entrada com timestamp
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"\n## [{timestamp}] Evento\n\n{content}\n"

        with open(full_path, "a", encoding="utf-8") as f:
            f.write(entry)

        # Re-ingerir o arquivo
        return self.ingest_file(filename, "episodic", environment_id)

    def add_procedural_entry(self, section, content):
        """Adiciona entrada na memória procedural (TOOLS.md)."""
        return self._append_to_file("TOOLS.md", section, content, "procedural")

    def _append_to_file(self, filename, section, content, chunk_type, environment_id=None):
        """Appenda seção em arquivo .md e re-ingere."""
        full_path = os.path.join(self.memory_dir, filename)

        entry = f"\n\n## {section}\n\n{content}\n"

        with open(full_path, "a", encoding="utf-8") as f:
            f.write(entry)

        return self.ingest_file(filename, chunk_type, environment_id)

    # =================================================================
    # MEMÓRIA DE TRABALHO (SESSÃO)
    # =================================================================

    def start_session(self, environment_id=None):
        """Inicia uma sessão do agente. Retorna session_id."""
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S_") + hashlib.md5(
            os.urandom(16)
        ).hexdigest()[:8]

        conn = self._get_conn()
        conn.execute(
            "INSERT INTO agent_sessions (session_id, environment_id) VALUES (?, ?)",
            (session_id, environment_id)
        )
        conn.commit()

        logger.info("🧠 Sessão do agente iniciada: %s", session_id)
        return session_id

    def end_session(self, session_id, summary=None):
        """Encerra uma sessão do agente."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE agent_sessions SET ended_at = datetime('now'), summary = ? WHERE session_id = ?",
            (summary, session_id)
        )
        conn.commit()

        # Salvar transcript se houver summary
        if summary:
            transcript_path = os.path.join(self.memory_dir, "sessions", f"{session_id}.md")
            with open(transcript_path, "w", encoding="utf-8") as f:
                f.write(f"# Sessão {session_id}\n\n{summary}\n")

        logger.info("🧠 Sessão do agente encerrada: %s", session_id)

    def get_session(self, session_id):
        """Retorna dados de uma sessão."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM agent_sessions WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_sessions(self, limit=20):
        """Lista sessões recentes."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM agent_sessions ORDER BY started_at DESC LIMIT ?",
            (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]

    # =================================================================
    # ESTATÍSTICAS
    # =================================================================

    def get_stats(self):
        """Retorna estatísticas da memória do agente."""
        conn = self._get_conn()
        cursor = conn.cursor()

        # Total de chunks por tipo
        cursor.execute("""
            SELECT chunk_type, COUNT(*) as count
            FROM chunks_meta
            GROUP BY chunk_type
        """)
        by_type = {row["chunk_type"]: row["count"] for row in cursor.fetchall()}

        # Total de chunks por arquivo
        cursor.execute("""
            SELECT source_file, COUNT(*) as count
            FROM chunks_meta
            GROUP BY source_file
            ORDER BY count DESC
        """)
        by_file = {row["source_file"]: row["count"] for row in cursor.fetchall()}

        # Tamanho do banco
        db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0

        # Total de buscas
        cursor.execute("SELECT COUNT(*) as total FROM search_log")
        total_searches = cursor.fetchone()["total"]

        # Total de sessões
        cursor.execute("SELECT COUNT(*) as total FROM agent_sessions")
        total_sessions = cursor.fetchone()["total"]

        # Última ingestão
        cursor.execute("SELECT MAX(created_at) as last FROM chunks_meta")
        row = cursor.fetchone()
        last_ingest = row["last"] if row else None

        # Arquivos .md disponíveis
        md_files = self._list_md_files()

        return {
            "total_chunks": sum(by_type.values()),
            "chunks_by_type": by_type,
            "chunks_by_file": by_file,
            "db_size_bytes": db_size,
            "db_size_mb": round(db_size / (1024 * 1024), 2),
            "total_searches": total_searches,
            "total_sessions": total_sessions,
            "last_ingest": last_ingest,
            "md_files": md_files
        }

    def get_recent_episodes(self, days=7, limit=20):
        """Retorna episódios recentes (últimos N dias)."""
        conn = self._get_conn()
        cursor = conn.cursor()

        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        cursor.execute("""
            SELECT chunk_id, source_file, section_title, content, created_at
            FROM chunks_meta
            WHERE chunk_type = 'episodic' AND created_at >= ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (since, limit))

        return [dict(row) for row in cursor.fetchall()]

    # =================================================================
    # ARQUIVOS DE MEMÓRIA
    # =================================================================

    def _list_md_files(self):
        """Lista todos os arquivos .md no diretório de memória."""
        files = []
        for root, _, filenames in os.walk(self.memory_dir):
            for filename in sorted(filenames):
                if filename.endswith(".md"):
                    rel_path = os.path.relpath(os.path.join(root, filename), self.memory_dir)
                    full_path = os.path.join(root, filename)
                    files.append({
                        "path": rel_path,
                        "size": os.path.getsize(full_path),
                        "modified": datetime.fromtimestamp(
                            os.path.getmtime(full_path)
                        ).isoformat()
                    })
        return files

    def read_file(self, rel_path):
        """Lê conteúdo de um arquivo .md da memória.

        Valida que o path está dentro de memory/ (prevenção de path traversal).
        """
        # Segurança: resolver path e garantir que está dentro de memory/
        full_path = os.path.normpath(os.path.join(self.memory_dir, rel_path))
        if not full_path.startswith(os.path.normpath(self.memory_dir)):
            raise ValueError("Acesso negado: path fora do diretório de memória")

        if not os.path.isfile(full_path):
            return None

        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()

    def list_files(self):
        """Lista arquivos de memória com metadados."""
        return self._list_md_files()

    # =================================================================
    # DICIONÁRIO SX2 (TABELAS PROTHEUS)
    # =================================================================

    def import_sx2(self, csv_path):
        """Importa tabelas do Protheus a partir de CSV da SX2.

        Ignora tabelas iniciadas por Z (customizações do cliente).
        Formato: alias;path;prefix;desc_pt;desc_es;desc_en;...
        """
        if not os.path.isfile(csv_path):
            logger.warning("Arquivo SX2 não encontrado: %s", csv_path)
            return 0

        conn = self._get_conn()
        cursor = conn.cursor()

        # Limpar dados anteriores
        cursor.execute("DELETE FROM sx2_tables")

        count = 0
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            for line in f:
                parts = line.split(";")
                if len(parts) < 6:
                    continue

                alias = parts[0].strip().strip('"').upper()

                # Ignorar tabelas customizadas (Z*)
                if alias.startswith("Z"):
                    continue

                # Ignorar se alias vazio ou muito curto
                if len(alias) < 2:
                    continue

                desc_pt = parts[3].strip().strip('"').strip()
                desc_en = parts[5].strip().strip('"').strip()
                prefix = parts[2].strip().strip('"').strip()

                if not desc_pt:
                    continue

                try:
                    cursor.execute(
                        "INSERT OR REPLACE INTO sx2_tables (alias, description_pt, description_en, prefix) VALUES (?, ?, ?, ?)",
                        (alias, desc_pt, desc_en or None, prefix or None)
                    )
                    count += 1
                except Exception:
                    pass

        conn.commit()
        logger.info("📋 SX2 importada: %d tabelas (excluídas Z*)", count)
        return count

    def search_sx2(self, query, limit=20):
        """Busca tabelas na SX2 por alias ou descrição."""
        conn = self._get_conn()
        cursor = conn.cursor()

        query_upper = query.upper().strip()

        # Busca exata por alias primeiro
        cursor.execute(
            "SELECT alias, description_pt, description_en FROM sx2_tables WHERE alias = ?",
            (query_upper,)
        )
        exact = cursor.fetchone()
        if exact:
            return [dict(exact)]

        # Busca por LIKE (alias ou descrição)
        cursor.execute("""
            SELECT alias, description_pt, description_en
            FROM sx2_tables
            WHERE alias LIKE ? OR description_pt LIKE ?
            ORDER BY alias
            LIMIT ?
        """, (f"%{query_upper}%", f"%{query}%", limit))

        return [dict(row) for row in cursor.fetchall()]

    def get_sx2_stats(self):
        """Retorna estatísticas da SX2 importada."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as total FROM sx2_tables")
        total = cursor.fetchone()["total"]

        # Contar por família (primeira letra)
        cursor.execute("""
            SELECT SUBSTR(alias, 1, 1) as family, COUNT(*) as count
            FROM sx2_tables
            GROUP BY family
            ORDER BY count DESC
            LIMIT 20
        """)
        families = {row["family"]: row["count"] for row in cursor.fetchall()}

        return {"total": total, "families": families}

    # =================================================================
    # MANUTENÇÃO
    # =================================================================

    def rebuild_index(self):
        """Reconstrói índice FTS5 do zero — limpa e re-ingere tudo."""
        conn = self._get_conn()
        cursor = conn.cursor()

        # Limpar tudo
        cursor.execute("DELETE FROM chunks_meta")
        # Rebuild FTS5
        cursor.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild')")
        conn.commit()

        # Re-ingerir
        results = self.ingest_all()

        logger.info("🔄 Índice FTS5 reconstruído: %s", results)
        return results

    def cleanup_old_sessions(self, days=30):
        """Remove sessões antigas (mais de N dias)."""
        conn = self._get_conn()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM agent_sessions WHERE ended_at IS NOT NULL AND ended_at < ?",
            (cutoff,)
        )
        deleted = cursor.rowcount
        conn.commit()

        logger.info("🧹 Sessões antigas removidas: %d", deleted)
        return deleted

    def get_search_history(self, limit=50):
        """Retorna histórico de buscas recentes."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM search_log ORDER BY searched_at DESC LIMIT ?",
            (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]


# =================================================================
# SINGLETON — instância global do service
# =================================================================

_instance = None


def get_agent_memory():
    """Retorna instância singleton do AgentMemoryService."""
    global _instance
    if _instance is None:
        _instance = AgentMemoryService()
    return _instance
