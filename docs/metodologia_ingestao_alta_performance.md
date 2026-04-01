# Metodologia de Ingestão de Alta Performance para Dados Tabulares em Python + SQLite

## O Problema

Processar ~2000 arquivos fonte (ADVPL/TLPP) e ~400K registros de CSVs (dicionário de dados ERP) sem estourar a memória RAM, mantendo velocidade aceitável.

**Cenário inicial:** o processo travava o PC consumindo toda a RAM disponível (~16GB) e não completava.

**Cenário final:** 1987 arquivos processados em 2.8 segundos, RAM máxima de 44MB, zero erros.

---

## As 7 Técnicas Utilizadas

### 1. Fast Path de Encoding (evitar chardet)

**Problema:** A biblioteca `chardet` lê o arquivo inteiro para detectar o encoding — lento e consome memória.

**Solução:** Como 99% dos arquivos Protheus são `cp1252` (Windows-1252), tentar decodificar direto sem detecção:

```python
def read_file(file_path):
    raw = file_path.read_bytes()
    if not raw:
        return ""
    # Fast path: tenta cp1252 direto (99% dos casos)
    try:
        return raw.decode("cp1252")
    except UnicodeDecodeError:
        pass
    # Fast path 2: tenta utf-8
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    # Slow path: chardet só como último recurso, e só nos primeiros 4KB
    detected = chardet.detect(raw[:4096])
    encoding = detected.get("encoding") or "latin-1"
    try:
        return raw.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        return raw.decode("latin-1")  # latin-1 nunca falha
```

**Ganho:** ~50x mais rápido por arquivo. Chardet em arquivo de 100KB levava ~50ms. Decode direto leva <1ms.

---

### 2. Commit por Arquivo (não por batch)

**Problema:** O SQLite acumula todas as inserções na RAM até o `commit()`. Se você insere 10.000 registros sem commitar, tudo fica na memória.

**Solução:** Commitar após cada arquivo processado:

```python
for file in files:
    content = read_file(file)
    chunks = split_into_chunks(content)

    db.executemany(
        'INSERT OR REPLACE INTO chunks VALUES (?,?,?,?,?)',
        chunks
    )
    db.commit()  # Libera o buffer de transação a cada arquivo

    del content, chunks  # Libera referências imediatamente
```

**Ganho:** RAM estável em ~40MB em vez de crescer indefinidamente.

---

### 3. Liberação Explícita de Memória (del + gc.collect)

**Problema:** O Python não libera memória automaticamente entre iterações de um loop. As strings do arquivo anterior ficam vivas até o garbage collector rodar.

**Solução:** Liberar explicitamente e forçar GC a cada N iterações:

```python
import gc

for i, file in enumerate(files):
    raw = file.read_bytes()
    content = raw.decode('cp1252')
    del raw  # Libera os bytes brutos IMEDIATAMENTE

    # ... processa ...

    del content, chunks, tuples  # Libera tudo

    if (i + 1) % 200 == 0:
        gc.collect()  # Força garbage collection periódica
```

**Ganho:** Evita acúmulo de 3-4 cópias da mesma string na memória.

---

### 4. PRAGMAs do SQLite para Performance

**Problema:** O SQLite por padrão prioriza segurança (fsync a cada write). Para ingestão em batch, isso é desnecessário.

**Solução:** Configurar PRAGMAs antes da ingestão:

```python
db.execute("PRAGMA journal_mode=WAL")      # Write-Ahead Logging (leitura + escrita simultânea)
db.execute("PRAGMA synchronous=NORMAL")     # Não faz fsync a cada write
db.execute("PRAGMA cache_size=2000")        # Cache de 2000 páginas (~8MB)

# ... processar tudo ...

db.execute("PRAGMA synchronous=FULL")       # Volta ao modo seguro depois
```

**Ganho:** ~3x mais rápido nas escritas.

---

### 5. executemany em vez de execute em loop

**Problema:** Chamar `db.execute()` para cada registro tem overhead de chamada Python → SQLite.

**Solução:** Montar lista de tuplas e usar `executemany`:

```python
# LENTO: 1 chamada por registro
for chunk in chunks:
    db.execute('INSERT INTO t VALUES (?,?,?)', (chunk['id'], chunk['name'], chunk['content']))

# RÁPIDO: 1 chamada para N registros
tuples = [(c['id'], c['name'], c['content']) for c in chunks]
db.executemany('INSERT INTO t VALUES (?,?,?)', tuples)
```

**Ganho:** ~5x mais rápido para batches grandes.

---

### 6. Sanitização de Encoding (surrogates)

**Problema:** Alguns CSVs (especialmente SX7) contêm caracteres surrogate (`\udd8a`) que o SQLite rejeita com `UnicodeEncodeError`.

**Solução:** Sanitizar ANTES de inserir:

```python
def sanitize_text(text):
    """Remove surrogates e outros Unicode inválidos."""
    return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")

# No parser de CSV:
def read_csv(file_path):
    with open(file_path, encoding='cp1252', errors='replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Sanitiza todos os valores string
            clean = {k: sanitize_text(v) if isinstance(v, str) else v
                     for k, v in row.items()}
            yield clean
```

**Ganho:** Zero erros de encoding. Antes falhava no registro 3262 de 18051.

---

### 7. Processamento em 2 Passadas (metadados + dados)

**Problema:** Extrair metadados (nomes de funções, tabelas referenciadas) e conteúdo (código fonte) ao mesmo tempo consome muita memória.

**Solução:** Separar em 2 passadas:

```python
# PASS 1: Só metadados (leve — ~1KB por arquivo)
for file in files:
    content = read_file(file)
    metadata = {
        'funcoes': extract_functions(content),      # Lista de nomes
        'tabelas': extract_tables(content),          # Lista de aliases
        'lines_of_code': count_lines(content),       # 1 número
    }
    db.execute('INSERT INTO fontes ...', metadata)
    db.commit()
    del content, metadata

# PASS 2: Chunks de código (pesado — ~4KB por função)
for file in files:
    raw = file.read_bytes()
    content = raw.decode('cp1252')
    del raw

    chunks = split_by_function(content, file.name)
    tuples = [(c['id'], file.name, c['func'], c['content'][:4000]) for c in chunks]
    del content, chunks

    db.executemany('INSERT INTO chunks ...', tuples)
    db.commit()
    del tuples
```

**Ganho:** Pass 1 roda em 25s com 65MB RAM. Pass 2 roda em 2.8s com 44MB RAM. Isolados, nenhum dos dois estressa a memória.

---

## Resultados

| Métrica | Antes | Depois |
|---------|-------|--------|
| **Tempo total** | Não completava (crash) | **28 segundos** |
| **RAM máxima** | >16GB (travava PC) | **65MB** |
| **Erros** | Crash por memória + encoding | **0** |
| **Registros processados** | Parcial | **342K registros + 8555 chunks** |

---

## Resumo

As 3 técnicas mais impactantes:

1. **Commit por arquivo** — controla o uso de RAM do SQLite
2. **Fast path de encoding** — elimina 99% do overhead de detecção
3. **del explícito + gc.collect** — força liberação de memória entre iterações

A filosofia geral: **processe pouco de cada vez, libere imediatamente, nunca acumule**.
