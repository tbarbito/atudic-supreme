# Descoberta Automática de Processos do Cliente

**Data:** 2026-03-26
**Status:** Em refinamento

---

## Objetivo

Criar uma camada de inteligência que, a partir dos dados já ingeridos no banco (fontes, campos, gatilhos, vínculos, jobs), **descubra automaticamente os macro-processos de negócio do cliente** sem que ninguém precise informar.

Isso permite que o Analista, ao receber uma demanda como "criar campo na SC5", saiba que existe aprovação de pedido, integração com Taura, motor de regras, etc. — e avise os riscos antes de montar artefatos.

---

## Princípios

1. **SQL primeiro** — extrair o máximo possível sem LLM
2. **LLM só pra classificar** — dar nome e descrição a padrões já detectados
3. **Cache por cliente** — rodar uma vez, cachear no banco, recalcular só no re-ingest
4. **Evidência antes de conclusão** — cada processo detectado tem lista de evidências concretas
5. **Padrão Protheus como referência** — o dicionário padrão (padrao_*) é a base; o que o cliente mudou/adicionou revela os processos

---

## Pipeline: 5 Passos

```
Base do cliente inteira (todas as tabelas)
  │
  ├─ Passo 1: Descoberta de processos (varredura completa)  [SQL]
  ├─ Passo 2: Mapa de gatilhos e cadeias                    [SQL]
  ├─ Passo 3: Fontes de escrita + tabelas satélite           [SQL]
  ├─ Passo 4: Jobs, schedules e criticidade                  [SQL]
  │
  ├─ Cache existe e está válido? → retorna cache
  │
  └─ Passo 5: Classificação e nomeação de processos         [LLM — 1 chamada]
       │
       └─ Salva no banco (tabela processos_detectados)
```

---

## Armazenamento

### Tabela `processos_detectados` (por cliente)

```sql
CREATE TABLE processos_detectados (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,              -- "Integração Taura WMS"
    tipo TEXT NOT NULL,              -- workflow, integracao, fiscal, logistica, etc
    descricao TEXT,                  -- "Pedidos enviados ao Taura com controle de status"
    criticidade TEXT,                -- alta, media, baixa
    tabelas JSON,                   -- ["SC5", "ZZE", "ZFZ"]
    evidencias JSON,                -- campos, fontes, gatilhos, tabelas_custom, jobs
    metodo TEXT,                    -- "cbox", "titulo", "nome_tabela", "prefixo", "llm"
    score REAL,                     -- confiança 0-1
    validado INTEGER DEFAULT 0,     -- 0=auto, 1=confirmado pelo consultor
    created_at TEXT DEFAULT (datetime('now'))
);
```

O dicionário padrão (`padrao_*`) e a tabela `diff` já existem no banco e servem como referência global — não precisamos de tabela de patterns separada.

---

## Passo 1 — Descoberta de Processos do Cliente

### Objetivo
Identificar os macro-processos de negócio do cliente analisando o que ele customizou em relação ao padrão Protheus.

### Base de referência
O padrão Protheus (tabelas `padrao_*`) + tabela `diff` + campos/tabelas custom.

### Abordagem
Em vez de patterns fixos por nome de campo (frágil), usamos **5 níveis de detecção** que analisam dados semânticos (títulos, cbox, nomes de tabela):

### Nível 1 — Tabelas custom (o nome revela o processo)

**Lógica:** Tabelas com `custom=1` têm nomes descritivos que já dizem o processo.

```sql
SELECT t.codigo, t.nome, COUNT(c.campo) as total_campos
FROM tabelas t
LEFT JOIN campos c ON c.tabela = t.codigo
WHERE t.custom=1
GROUP BY t.codigo
HAVING total_campos >= 5
ORDER BY total_campos DESC;
```

**Resultado validado (Marfrig):**
- ZZE (62 campos) → "INTEGRACAO TAURA - PRODUCAO"
- ZC5 (63 campos) → "CABECALHO PEDIDOS SFA"
- ZAV (54 campos) → "RAMI" (veterinário)
- ZZM (46 campos) → "PEDIDO DE ABATE MESTRE"
- ZZR (46 campos) → "CERTIFICACAO SANITARIA"
- SZ1 (28 campos) → "MONITOR DE INTEGRACOES"
- ZEA (28 campos) → "Regras de aprov. Automatica"

**Custo:** ZERO (1 query SQL)

---

### Nível 2 — Cbox dos campos custom (revela máquinas de estado)

**Lógica:** Campos com combobox de 3+ valores revelam fluxos/estados de processo. O conteúdo do cbox é mais confiável que o nome do campo.

```sql
SELECT tabela, campo, titulo, cbox,
    LENGTH(cbox) - LENGTH(REPLACE(cbox, ';', '')) + 1 as num_estados
FROM campos
WHERE custom=1 AND cbox IS NOT NULL AND LENGTH(cbox) > 3
AND LENGTH(cbox) - LENGTH(REPLACE(cbox, ';', '')) >= 2
ORDER BY num_estados DESC;
```

**Classificação automática por conteúdo do cbox:**
- cbox com "Pendente/Aprovado/Rejeitado" → workflow
- cbox com "Pendente/Integrado/Erro" → pipeline integração
- cbox com "Sim/Nao" em 5+ campos da mesma tabela → flags de controle

**Resultado validado (Marfrig):**
- ZGX_STATUS: 9 estados (Pendente→PreAprov→Aprovado→Reprovado→Autorizado→Congelado→Cancelado→Finalizado→Alocado) → **Workflow RAME completo**
- ZJU_STATUS: 8 estados → **Pipeline pedido compra**
- ZB1_CAD: 8 tipos de cadastro → **Aprovação multi-cadastro**
- NT2_XAPROV: 6 estados (Pendente Jur.→Pendente CAP→...) → **Aprovação jurídica 2 níveis**
- ZAV: 5 áreas com 3 estados cada (Comercial, Qualidade, Transporte, Expedição, PCP) → **RAMI com 5 áreas aprovando**

**Custo:** ZERO (1 query SQL)

---

### Nível 3 — Títulos dos campos custom (linguagem humana)

**Lógica:** O título (X3_TITULO) é texto legível que descreve o campo. Muito mais confiável que o nome abreviado. Agrupar por palavras-chave no título.

```sql
-- Classificar campos custom por palavras-chave no título
SELECT
    CASE
        WHEN LOWER(titulo) LIKE '%aprov%' OR LOWER(titulo) LIKE '%liber%' THEN 'WORKFLOW_APROVACAO'
        WHEN LOWER(titulo) LIKE '%bloq%' THEN 'CONTROLE_BLOQUEIO'
        WHEN LOWER(titulo) LIKE '%integr%' THEN 'INTEGRACAO'
        WHEN LOWER(titulo) LIKE '%envia%' OR LOWER(titulo) LIKE '%reenvi%' THEN 'ENVIO_INTEGRACAO'
        WHEN LOWER(titulo) LIKE '%status%' THEN 'STATUS_PROCESSO'
        WHEN LOWER(titulo) LIKE '%log de%' THEN 'AUDITORIA_LOG'
        WHEN LOWER(titulo) LIKE '%taura%' THEN 'TAURA_WMS'
        WHEN LOWER(titulo) LIKE '%tms%' THEN 'TMS_TRANSPORTE'
        WHEN LOWER(titulo) LIKE '%rami%' THEN 'RAMI_VETERINARIO'
        -- ... mais padrões
    END as processo,
    COUNT(*) as qtd_campos,
    GROUP_CONCAT(DISTINCT tabela) as tabelas
FROM campos
WHERE custom=1 AND titulo IS NOT NULL
GROUP BY processo
HAVING processo IS NOT NULL;
```

**Resultado validado (Marfrig):**

| Processo | Campos | Tabelas afetadas |
|----------|:------:|-----------------|
| AUDITORIA_LOG | 555 | 250+ tabelas |
| ENVIO_INTEGRACAO | 58 | SC5, SA1, SA2, SB1... |
| STATUS_PROCESSO | 49 | SE1, SE2, SC5, NT2... |
| INTEGRACAO | 38 | SA1, SA2, SB1, SC5... |
| FRETE_TRANSPORTE | 33 | DAK, SA4, GW3... |
| RAMI_VETERINARIO | 29 | EEC, SC5, SC6, SD1 |
| TAURA_WMS | 24 | SC5, SA2, SB1, SC7... |
| WORKFLOW_APROVACAO | 22 | SA1, SA2, SC5, SC7... |
| CONTROLE_BLOQUEIO | 20 | SC5, SF4, SE2, SA1... |
| ECOMMERCE | 20 | XC6, SA1, SC5, SE1... |
| SALESFORCE | 11 | SA1, SC5, DA0, SC7... |
| TMS_TRANSPORTE | 2 | SC5 |

**Custo:** ZERO (1 query SQL)

---

### Nível 4 — Prefixo repetido em tabelas padrão (detecta sistemas externos)

**Lógica:** 4+ campos custom com mesmo prefixo numa tabela padrão = sistema externo integrado.

```sql
-- Agrupar campos custom por prefixo (3-4 chars após alias)
-- C5_ZTAU* → prefixo "TAU"
-- C5_ZTMS* → prefixo "TMS"
```

**Resultado validado:** C5_ZTAU* (5+ campos) = Taura, C5_ZTMS* (5+ campos) = TMS, C5_ZDEP* (7+ campos) = Depósito

**Custo:** ZERO

---

### Nível 5 — Diff padrão vs cliente

**Lógica:** A tabela `diff` mostra o que o cliente ADICIONOU e ALTEROU em relação ao padrão.

```sql
SELECT tabela,
    SUM(CASE WHEN acao='adicionado' THEN 1 ELSE 0 END) as adicionados,
    SUM(CASE WHEN acao='alterado' THEN 1 ELSE 0 END) as alterados,
    COUNT(*) as total_diffs
FROM diff WHERE tipo_sx='campo'
GROUP BY tabela
HAVING total_diffs >= 20
ORDER BY total_diffs DESC;
```

**Resultado validado:** SC5 tem 184 campos adicionados + 11 alterados. SB1 tem 79 adicionados + 39 alterados (39 validações mudadas = tabela "blindada").

**Custo:** ZERO

---

### Resumo Passo 1

- Roda na **base inteira** do cliente, não por tabela individual
- **100% SQL** — zero custo de LLM
- Resultado: lista de clusters com evidências, prontos pro Passo 5 classificar
- **Validado na Marfrig:** detectou 20+ processos sem ninguém informar nada

---

## Passo 2 — Mapa de Gatilhos e Cadeias

### O que faz
Analisa gatilhos custom para descobrir fluxos de preenchimento automático e dependências entre campos/tabelas.

### Por que funciona
Gatilhos revelam a **cadeia de causa-efeito**: quando C5_CLIENTE muda, 17 campos são preenchidos automaticamente, incluindo chamadas a funções U_ que fazem lógica de negócio. Essa cadeia É o processo.

### O que extrai

1. **Super-triggers:** Campos que disparam 5+ gatilhos = ponto central do processo
2. **Funções chamadas:** U_ functions nas regras dos gatilhos = lógica de negócio
3. **Tabelas consultadas:** Alias diferentes da tabela alvo = dependências externas
4. **Gatilhos com regra custom:** regra_customizada=1 = cliente mudou lógica padrão
5. **Cadeia transitiva:** C5_CLIENTE → C5_TIPO → C5_ZTIPPED → 4 campos

### Exemplo real (SC5 Marfrig)
```
C5_CLIENTE → 17 gatilhos:
  ├── C5_XORIGEM (origem fixa)
  ├── C5_ZMDCTR via U_MGFFAT33() (contrato)
  ├── C5_ZREVIS via U_MGFFAT33() (revisão)
  ├── C5_ZMDPLAN via U_MGFFAT33() (planilha)
  ├── C5_ZDESC via U_MGFFAT33() (desconto)
  ├── C5_XCGCCPF (CNPJ do cliente)
  ├── C5_ZCONDPA (cond. pagamento)
  ├── C5_ZCROAD via u_MGFSZ9ID() (RoadNet)
  └── ... mais 8
```

### Output
```json
{
  "total_gatilhos_custom": 70,
  "super_triggers": {
    "C5_CLIENTE": {"qtd_destinos": 17, "funcoes": ["U_MGFFAT33", "U_MGFFAT99"]},
    "C6_PRODUTO": {"qtd_destinos": 9, "funcoes": ["U_T05Descont", "U_MGFFATAF"]}
  },
  "funcoes_chamadas": ["U_MGFFAT33", "U_T05Descont", "U_MGFFAT99"],
  "tabelas_consultadas": ["SB1", "SA1", "SZ9", "SZC", "ZM0"]
}
```

### Pontos em aberto
- Seguir cadeia transitiva? (C5_CLIENTE → C5_TIPO → C5_ZTIPPED → 4 campos)
- Gatilhos padrão alterados (regra_customizada=1) vs custom puros
- Analisar as U_ functions via funcao_docs?

**Custo:** ZERO (SQL puro)

---

## Passo 3 — Fontes de Escrita + Tabelas Satélite

### O que faz
Descobre todos os programas que escrevem na tabela, o que cada um faz, e quais tabelas custom auxiliares estão envolvidas.

### Por que funciona
Cada programa que escreve na tabela é um **ponto de entrada do processo**. Se MGFWSCAR.prw escreve na SC5 e também escreve na ZKQ, a ZKQ é uma tabela satélite desse processo.

### O que extrai

1. **Fontes de escrita** com propósito (reusa dados existentes do banco, sem LLM)
2. **Tipo de escrita:** ExecAuto, RecLock, ou ambos
3. **PEs implementados** nesses fontes
4. **Tabelas satélite:** tabelas custom escritas pelos mesmos fontes
5. **Funções U_ chamadas** por esses fontes (calls_u)

### Tabelas satélite — o que revelam
```
Fonte escreve SC5 + ZKQ → ZKQ é satélite de integração WS
Fonte escreve SC5 + SZV → SZV é satélite de aprovação
Fonte escreve SC5 + ZHL → ZHL é satélite de histórico de regras
Fonte escreve SC5 + ZH3 → ZH3 é satélite de carrinho e-commerce
```

### Tabela `operacoes_escrita` — dados estruturados de escrita

Adicionada ao pipeline de ingestão (fase 2, pass 1). Para cada RecLock, TcSqlExec ou dbDelete encontrado nos fontes, extrai:

- **arquivo/funcao**: onde está a operação
- **tipo**: `reclock_inc` (inclusão), `reclock_alt` (alteração), `db_delete`, `sql_delete`, `sql_update`
- **tabela**: tabela alvo
- **campos**: JSON com campos escritos no bloco
- **origens**: JSON mapeando campo → origem do valor (`tela:M->`, `variavel:`, `literal:`, `tabela:ALIAS->`, `funcao:`)
- **condicao**: IF que envolve o RecLock (ex: `bEmite`, `NOT (bEmite)`)
- **linha**: número da linha no fonte

**Resultado na Marfrig:** 2.528 operações extraídas de 656 fontes em 31 segundos.

**Impacto:** Resolveu caso real onde busca em `fonte_chunks` (texto truncado a 4000 chars) não encontrou quem gravava ZZM_VLDESC. A query estruturada encontra em <1ms:

```sql
SELECT arquivo, funcao, tipo, condicao, origens
FROM operacoes_escrita
WHERE tabela = 'ZZM' AND campos LIKE '%ZZM_VLDESC%';
```

Retorna 3 pontos de escrita com origem e condição — informação que antes exigia leitura manual de código.

**Custo:** ZERO (regex puro no pipeline, sem LLM)

---

## Passo 4 — Jobs, Schedules e Criticidade

### O que faz
Cruza os fontes do passo 3 com jobs/schedules pra identificar processos automáticos e sua frequência.

### Por que funciona
Um job que roda a cada 30 segundos em 11 instâncias (MGFWSCAR) é muito mais crítico que um relatório manual. A frequência revela a criticidade.

### Classificação de criticidade
```
Crítico:   refresh_rate < 60s OU instâncias > 5
Alto:      refresh_rate 60-300s OU instâncias 3-5
Médio:     refresh_rate 300-1800s OU instâncias 1-2
Baixo:     refresh_rate > 1800s OU schedule inativo
```

**Custo:** ZERO (SQL puro)

---

## Passo 5 — Classificação e Nomeação (LLM — 1 chamada)

### O que faz
Recebe os dados estruturados dos passos 1-4 e classifica em processos de negócio nomeados.

### Por que precisa de LLM
A heurística detecta "7 campos com prefixo TAU + 1 fonte WebService + 3 jobs a 30s" mas só a interpretação semântica sabe dizer "isso é uma integração com WMS Taura pra logística de armazém".

### Tipos de processo
| Tipo | Descrição |
|------|-----------|
| workflow | Aprovação, liberação, bloqueio |
| integracao | Sistema externo bidirecional |
| pricing | Preços, descontos, contratos |
| fiscal | Exportação, tributação especial |
| logistica | Roteirização, depósito, embarque |
| regulatorio | Sanitário, veterinário, certificação |
| auditoria | Log, rastreamento de alterações |
| qualidade | Inspeção, não-conformidade, APQP |
| automacao | Jobs, processos batch |
| outro | Não se encaixa nos anteriores |

### Cache
- Salvar resultado na tabela `processos_detectados`
- Invalidar quando: novo ingest de fontes OU alteração de campos custom
- **Custo LLM: 1 vez por cliente** (não por tabela, roda na base inteira)

---

## Próximos passos

- [x] Validar Passo 1 na base Marfrig (20+ processos detectados)
- [x] Validar Passo 2 na SC5/SC6 (70 gatilhos custom, super-triggers mapeados)
- [x] Criar tabela `operacoes_escrita` com extração estruturada de RecLock/SQL
- [x] Ingerir 1.987 fontes → 2.528 operações (31s, 0 erros)
- [x] Validar caso real: ZZM_VLDESC encontrado em <1ms (3 pontos de escrita)
- [ ] Refinar e validar Passo 4 (jobs)
- [ ] Definir prompt do Passo 5 (LLM)
- [ ] Definir como o Analista consome os processos detectados
- [ ] Implementar pipeline completo como tool do Analista
