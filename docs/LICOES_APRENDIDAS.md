# Lições Aprendidas — ExtraiRPO / Protheus Toolkit

> Documento de referência para futuros projetos envolvendo engenharia reversa de ERP,
> ingestão de dados em massa, parsing de código legado e geração de documentação com IA.
>
> Última atualização: 2026-03-23

---

## 1. Encoding — A Armadilha Silenciosa

### 1.1 Fast-path de detecção (50x mais rápido que chardet)

99% dos arquivos Protheus são **CP1252** (Windows-1252). Usar `chardet` direto em 2000 arquivos desperdiça ~100s.

```python
# Tente cp1252 primeiro (<1ms), utf-8 segundo, chardet só como fallback
for enc in ["cp1252", "utf-8"]:
    try:
        return raw.decode(enc)
    except UnicodeDecodeError:
        continue

# Fallback: chardet só nos primeiros 4KB (não no arquivo inteiro)
detected = chardet.detect(raw[:4096])
encoding = detected.get("encoding") or "latin-1"
```

**Por que importa:** chardet lê o arquivo inteiro (~50ms/100KB). Com fast-path, 99% resolve em <1ms.

### 1.2 Surrogates em CSV (o crash que aparece no registro 3262)

Arquivos CSV exportados do Protheus (especialmente SX7/gatilhos) contêm surrogates Unicode malformados (`\udd8a`) que o SQLite rejeita.

```python
def _sanitize_text(text: str) -> str:
    return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
```

**Antes:** crash no registro 3262/18051. **Depois:** 18051/18051 sem erro.

### 1.3 Round-trip de encoding ao modificar fontes

Ao injetar comentários (ex: ProtheusDoc) em .prw, **salve no encoding original**:

```python
# Lê detectando encoding
content, encoding = read_source(file_path)  # retorna ("...", "cp1252")

# Modifica o conteúdo
content = inject_doc(content, ...)

# Salva no MESMO encoding
file_path.write_bytes(content.encode(encoding, errors="replace"))
```

**Regra de ouro:** comentários injetados devem ser **ASCII + acentos portugueses**. Nada de emojis, setas (→), bullets (•).

### 1.4 BOM (Byte Order Mark)

Alguns arquivos têm UTF-8-BOM (`\xef\xbb\xbf`). Verifique antes de decodificar:

```python
if raw.startswith(b'\xef\xbb\xbf'):
    return raw[3:].decode('utf-8'), 'utf-8-sig'
```

---

## 2. Ingestão de Dados em Massa

### 2.1 Commit por arquivo, não por lote

SQLite acumula inserções em RAM até o commit. Fazendo commit a cada 1000 registros, a RAM cresce sem parar. Fazendo commit **a cada arquivo processado**, a RAM fica estável em ~44MB.

```python
for file in files:
    rows = parse(file)
    cursor.executemany("INSERT INTO ...", rows)
    conn.commit()  # Libera RAM a cada arquivo
```

**Resultado:** 1987 arquivos em 2.8s, pico de 44MB RAM.

### 2.2 Liberação explícita de memória

Python não libera strings automaticamente entre iterações. Use `del` + `gc.collect()` a cada ~200 iterações:

```python
for i, file in enumerate(files):
    content = file.read_text()
    process(content)
    del content
    if i % 200 == 0:
        gc.collect()
```

### 2.3 PRAGMAs SQLite para carga em lote

Antes de inserções massivas:

```python
cursor.execute("PRAGMA journal_mode=WAL")
cursor.execute("PRAGMA synchronous=NORMAL")
cursor.execute("PRAGMA cache_size=2000")
```

Depois, reverter para `synchronous=FULL`. Ganho: ~3x na velocidade.

### 2.4 executemany() > execute() em loop

`executemany()` reduz overhead Python→SQLite. ~5x mais rápido para lotes.

### 2.5 CSV com campos gigantes

Campos SX podem ter 10MB+. Configure globalmente:

```python
csv.field_size_limit(10_000_000)
```

### 2.6 Duas passadas é melhor que uma

- **Passada 1:** Metadados leves (nomes de função, tabelas referenciadas) — ~1KB/arquivo
- **Passada 2:** Chunks de código — transação separada

Isoladas, nenhuma estressa memória. Combinadas, podem chegar a 150MB+.

---

## 3. Parsing de Código ADVPL/TLPP

### 3.1 Detecção de funções — 3 patterns de regex

```python
# Funções padrão
r"(?:Static\s+|User\s+|Main\s+)?Function\s+(\w+)"
# WebService methods
r"WSMETHOD\s+(\w+)\s+WS(?:RECEIVE|SEND|SERVICE)"
# Métodos de classe
r"METHOD\s+(\w+)\s*\([^)]*\)\s*CLASS\s+\w+"
```

**Pré-compile o regex** — evita recompilação por arquivo.

**Limitação conhecida:** ~95% de acurácia. Linhas como `Local c := "Function Fake()"` geram falso-positivo, mas são raras o suficiente para não justificar um lexer completo.

### 3.2 Chunking com overlap

- `MAX_CHUNK_CHARS = 4000` (cabe no contexto do embedding)
- `OVERLAP_CHARS = 400` (previne perda de contexto nas bordas)
- Quebre por boundary de função, não por contagem de caracteres

### 3.3 Detecção de tabelas custom

- Prefixo **SZ\***, **QA\*-QZ\*** = custom
- Prefixo **SX\*** = metadados do dicionário (standard)
- Demais (SA1, SC5, SF2...) = standard

### 3.4 Classificação de módulo — 3 prioridades

1. **Nome da rotina** (melhor): MATA410 → faturamento (lookup em mapa-modulos.json)
2. **Overlap de tabelas** (universal): se usa SC5+SC6 → faturamento
3. **Prefixo do filename** (pior, cliente-específico): MGFFAT* → faturamento

**Atenção:** Prefixos de filename são convenção do cliente, não universais.

### 3.5 Detecção de ProtheusDoc existente

Olhe 30 linhas para trás a partir da declaração da função:

```python
start = max(0, func_line - 30)
block = '\n'.join(lines[start:func_line])
pattern = re.compile(r'\{Protheus\.doc\}\s*' + re.escape(func_name), re.IGNORECASE)
```

30 linhas é janela segura (cobre blank lines + bloco de comentário típico).

---

## 4. Web Scraping (TDN e Google)

### 4.1 Confluence renderiza com JS — CSS selectors com fallback

TDN usa Confluence. Conteúdo é renderizado client-side. Use Playwright e tente múltiplos seletores:

```python
selectors = [
    "#main-content", ".wiki-content", "#content .view",
    "article", ".confluence-information-macro", "body"
]
for sel in selectors:
    el = page.query_selector(sel)
    if el and el.inner_text().strip():
        return el.inner_text()
```

### 4.2 networkidle não basta

Após `wait_until="networkidle"`, adicione 2s de sleep. Confluence faz múltiplas renderizações JS.

### 4.3 Google: busque com site restriction

```
site:tdn.totvs.com MATA410
```

É mais rápido e confiável que a busca interna do TDN.

### 4.4 Limpe URLs de redirect do Google

Google encapsula links em `/url?q=...&sa=...`. Extraia a URL real:

```python
real_url = url.split("/url?q=")[1].split("&")[0]
```

### 4.5 User-Agent obrigatório

Google bloqueia scrapers headless. Sempre envie UA de browser real.

### 4.6 PARAMIXB — 5 estratégias de extração

Pontos de entrada documentam parâmetros PARAMIXB em formatos variados no TDN:

1. Tabelas tab-separated (formato Confluence)
2. Seções de observação com índices
3. Menções inline
4. Listas com bullet
5. Exemplos em código (comentários)

**Implemente todas as 5**, pois cada PE usa formato diferente.

### 4.7 Falha de rede = resultado vazio, não crash

```python
try:
    result = scrape_tdn(url)
except Exception:
    return {}  # melhor que crashar o pipeline inteiro
```

---

## 5. Integração com LLM

### 5.1 Estratégia dual-model (10x redução de custo)

| Estágio | Modelo | Custo | Para quê |
|---------|--------|-------|----------|
| 1 | Código puro | $0 | Metadados, listas de tabelas, triggers, campos — 35-40% do doc |
| 2-3 | GPT-4.1 | $$ | Catálogo de dados, análise de fontes — 30-40% |
| 4 | Claude Sonnet | $$$ | Síntese narrativa, fluxos, recomendações — 20% |

**Resultado:** ~$0.16/módulo vs ~$3-5 usando modelo caro para tudo.

**Princípio:** GPT-4.1 é ótimo para catalogar dados estruturados. Claude Sonnet excele em síntese narrativa e análise arquitetural.

### 5.2 Contexto > Prompt

A pergunta não é "como formulo o prompt?" mas sim:

> **Qual informação, em qual formato, em qual ordem, em qual momento o modelo precisa?**

Para cada estágio, forneça **exatamente**:

1. **Dados estruturados** (JSON com campos parseados, contagens, relações) — não dumps raw
2. **Janelas de contexto ordenadas por importância** — dados mais relevantes primeiro
3. **Instruções de formato, não exemplos** — "output Markdown com H2" gasta menos tokens que 3 exemplos
4. **Modos de falha explícitos** — "se não conseguir determinar, output 'desconhecido', não chute"

### 5.3 LiteLLM para abstração de provider

Use LiteLLM para não ficar preso a um provider. Mesma interface para Claude, GPT, Ollama:

```python
from litellm import completion
response = completion(model="anthropic/claude-sonnet-4-20250514", messages=[...])
```

Troca de modelo = troca de string, não de código.

### 5.4 Singleton para ChromaDB client

Criar novo client ChromaDB recarrega embeddings (2-3s). Cache com singleton:

```python
_client_cache = {}
def get_shared_client(persist_dir):
    key = str(persist_dir.resolve())
    if key not in _client_cache:
        _client_cache[key] = chromadb.PersistentClient(path=key)
    return _client_cache[key]
```

**Lazy import** do ChromaDB também evita carregar sentence-transformers no startup.

---

## 6. Arquitetura

### 6.1 Separe geração de chat

**Erro do v2:** Chat tentava classificar + gerar docs + responder perguntas no mesmo stream SSE.
**Resultado:** rate limit 429, docs não salvaram, servidor bloqueado.

**Solução v3:**
- `POST /api/generate` → pipeline dedicado, retorna quando termina
- `POST /api/chat` (SSE) → consulta docs já gerados + busca semântica

Geração é cara (múltiplas chamadas LLM). Chat é barato (busca vetorial + 1 chamada).

### 6.2 File-first para single-tenant

Markdown em disco + SQLite + ChromaDB funciona bem para:
- Uma instalação por cliente (consultor com laptop)
- Offline-first (sem dependência de cloud)
- Versionável com git

**Não** funciona para: multi-tenant SaaS, audit trail imutável, sync real-time.

### 6.3 Dual-layer de documentação (humano + ia)

- **Camada humano:** Markdown narrativo para analista ler
- **Camada ia:** YAML frontmatter + metadados estruturados para agentes consumirem

Mesmo conteúdo, dois formatos, dois públicos.

### 6.4 SSE para operações longas

Streaming Server-Sent Events mantém conexão viva enquanto backend processa. Frontend recebe updates a cada N segundos em vez de esperar timeout de 30s+.

**Limitação:** SSE é one-way. Para cancelamento, precisa WebSocket ou endpoint separado de cancel.

---

## 7. Erros Comuns e Armadilhas

### 7.1 Os 12 gotchas que mais doeram

| # | Gotcha | Solução |
|---|--------|---------|
| 1 | chardet é lento para bulk | Fast-path cp1252 → utf-8 → chardet |
| 2 | SQLite acumula RAM até commit | Commit por arquivo, não por lote |
| 3 | ChromaDB client é caro de criar | Singleton com cache |
| 4 | Campos CSV podem ter 10MB+ | `csv.field_size_limit(10_000_000)` |
| 5 | Web scraping falha frequentemente | Return vazio, nunca crash |
| 6 | Boundaries de função em ADVPL são ambíguos | Regex 95% é suficiente para MVP |
| 7 | BOM em UTF-8 | Checar `\xef\xbb\xbf` antes de decode |
| 8 | Surrogates em CSV | `encode('utf-8', errors='replace')` |
| 9 | Uma passada de ingestão explode memória | Duas passadas: metadados + conteúdo |
| 10 | Tweaking de prompt não resolve dados ruins | Contexto/dados corretos > prompt perfeito |
| 11 | Geração + chat no mesmo endpoint | Separar rotas e responsabilidades |
| 12 | Prefixos de arquivo são cliente-específicos | Não confie como classificação universal |
| 13 | Overlap em chunking causa loop infinito | Usar `start += step` fixo, nunca `start = end - overlap` |
| 14 | Backward walk com tracking de block comments | Classificar linhas uma vez (forward), backward walk só consulta ints |
| 15 | `region.split('\n')` para cada função explode memória | Line offset table + bisect: O(total_linhas) em vez de O(funções * região) |

### 7.3 Chunking com overlap — a armadilha do loop infinito

O padrão ingênuo de chunking com overlap:

```python
# BUG: quando end < start + MAX (última iteração), start recua e fica preso
while start < len(content):
    end = min(start + MAX, len(content))
    chunks.append(content[start:end])
    start = end - OVERLAP  # ← LOOP INFINITO se end não avança
```

**Solução:** usar step fixo que garante avanço:

```python
step = MAX - OVERLAP  # ex: 4000 - 400 = 3600
while start < len(content):
    end = min(start + MAX, len(content))
    chunks.append(content[start:end])
    start += step  # ← SEMPRE avança 3600 chars
```

**Por que importa:** Um chunk de 4080 chars (apenas 80 acima do limite de 4000) gerava loop infinito, criando sub_chunks até consumir 15GB+ de RAM. Difícil de diagnosticar porque só acontecia com chunks ligeiramente acima do limite.

### 7.4 Parsing eficiente de código-fonte — Line Offset Table

Para arquivos com muitas funções (95+), não faça `content[a:b].split('\n')` por função. Use:

1. **Uma passada:** `_build_line_offsets(content)` → array de ints com offset de cada linha
2. **Uma passada:** `_classify_lines()` → array de ints (0=code, 1=comment, 2=blank)
3. **bisect:** converte posição do regex → número de linha em O(log n)
4. **Backward walk:** consulta apenas `line_types[j]` (ints), zero cópias de string
5. **Slice final:** `content[start:end]` só quando monta o chunk

Memória: O(total_linhas) constante, independente do número de funções.

### 7.5 Padrão de graceful degradation

Para qualquer operação de rede ou parsing arriscado:

```python
try:
    result = risky_operation()
except Exception:
    return default_value  # [], {}, "", False
```

**Filosofia:** melhor retornar 0 resultados que crashar o pipeline. O chat pode dizer "informação não encontrada" em vez de error 500.

### 7.3 CSV: errors="replace" como padrão

```python
with open(path, "r", encoding=encoding, errors="replace") as f:
    reader = csv.DictReader(f)
```

Zero errors > 99% completion com crash.

---

## 8. Testes e Validação

### 8.1 Para projetos com IA, foque em:

1. **Determinismo do pipeline de dados** — parsers devem ser 100% corretos (testáveis)
2. **Prevenção de crash** — sem falhas silenciosas, erros explícitos
3. **Regressão** — fixtures + assertions em outputs conhecidos

**Não tente 100% coverage** em saídas de LLM — são probabilísticas por natureza.

### 8.2 Teste o parser, não o LLM

```python
def test_extract_functions():
    source = "User Function XFAT001()\nLocal x := 1\nReturn\n"
    funcs = extract_functions(source)
    assert funcs == [{"name": "XFAT001", "line": 1, "type": "User Function"}]
```

---

## 9. Segurança

### 9.1 API keys em config.json

**Anti-pattern:** API keys hardcoded no repositório. Para produção:
- Use variáveis de ambiente: `ANTHROPIC_API_KEY=...`
- Adicione `config.json` ao `.gitignore`
- Use secrets manager (AWS Secrets Manager, Vault)

### 9.2 Localhost-only

O servidor FastAPI deve escutar apenas em `127.0.0.1`, nunca `0.0.0.0`, quando usado como ferramenta local.

---

## 10. Checklist para Próximo Projeto Similar

Antes de começar um novo projeto de engenharia reversa de ERP com IA:

- [ ] Configurar fast-path de encoding (cp1252 → utf-8 → chardet)
- [ ] Implementar sanitização de surrogates para CSV
- [ ] Definir estratégia de commit por arquivo no SQLite
- [ ] Configurar PRAGMAs de performance no SQLite
- [ ] Separar endpoints de geração e consulta desde o início
- [ ] Implementar graceful degradation em todas as chamadas de rede
- [ ] Usar LiteLLM para abstração de provider
- [ ] Planejar dual-model (barato para dados, forte para síntese)
- [ ] Implementar singleton para ChromaDB client
- [ ] Definir chunking com overlap para embeddings
- [ ] Criar dual-layer de docs (humano + ia) desde o design
- [ ] Testar parsers com fixtures, não outputs de LLM
- [ ] Mover API keys para variáveis de ambiente

---

## Referências Internas

| Tema | Arquivo |
|------|---------|
| Performance de ingestão | `docs/metodologia_ingestao_alta_performance.md` |
| Encoding/ProtheusDoc | `docs/skill_protheusdoc.md` (seção 1) |
| Arquitetura de agentes | `AI_AGENT_ENGINEERING_GUIDELINE_v4.md` |
| Pipeline v3 | `backend/services/doc_pipeline_v3.py` |
| Parser de fontes | `backend/services/parser_source.py` |
| Parser de dicionário | `backend/services/parser_sx.py` |
| Scraper TDN | `backend/services/tdn_scraper.py` |
| Ingestor | `backend/services/ingestor.py` |
| Prompts estruturados | `backend/services/analista_prompts.md` |
| Vectorstore | `backend/services/vectorstore.py` |
