# Peca ao Analista — Design Spec

## Conceito

Nova view no ExtraiRPO onde o consultor/analista funcional descreve uma necessidade em linguagem natural. A IA conduz uma conversa investigativa, busca no banco com bom senso (filtrando so o relevante), e entrega dois outputs: documento gerencial (1 MD) e documentos tecnicos (N MDs).

**Publico**: Consultores funcionais e analistas de negocio que sabem do processo mas precisam da resposta tecnica.

## Principios

1. **Investigativa primeiro** — IA faz perguntas de negocio antes de buscar
2. **Busca silenciosa** — usa ferramentas internas sem expor complexidade
3. **Bom senso** — filtra ruido (ignora relatorios, leitura, so traz impacto real)
4. **Gera overviews faltantes** — se encontra fonte relevante sem overview, gera silenciosamente
5. **Multi-projeto** — cada projeto tem sua conversa/contexto separado
6. **Tom consultor senior** — direto, tecnico mas acessivel, sem enrolacao. Explica o "porque" quando pedido.

## Fluxo de Interacao

```
Usuario descreve necessidade
        |
IA faz perguntas de negocio (2-4 perguntas)
  "Qual modulo? Quem usa? Tem integracao?"
        |
IA investiga silenciosamente no banco
  - fontes que ESCREVEM na tabela (ignora leitura/relatorios)
  - PEs existentes na rotina
  - gatilhos e validacoes
  - gera overviews faltantes se relevante
        |
IA propoe solucao enxuta (chat limpo, sem detalhes tecnicos)
  "Pra isso voce vai precisar de X, Y e Z. Quer que eu detalhe?"
        |
Usuario ajusta / aprova
        |
Gera documentos:
  Projeto_Gerencial.md (1 arquivo)
  Tecnico_*.md (N arquivos)
```

## UI

### Tela Inicial — Cards de Projetos
- Ao entrar, ve cards dos projetos existentes + botao "Novo Projeto"
- Cada card: nome, data, status (badge), descricao curta
- Layout limpo, sem poluir (max 2 linhas por card)
- Click abre a conversa do projeto

### Tela do Projeto — Chat + Painel
```
+----------------------------------------------+---------------------------+
|  < Voltar     Projeto: Campo Alcada SC5      |  Artefatos do Projeto     |
|----------------------------------------------+---------------------------+
|                                              |  [v] Campos (2)           |
|  User: Preciso criar um campo de alcada...   |    + A1_XALCAD (SA1)      |
|                                              |    + C5_XAPROV (SC5)      |
|  IA: Entendi. Algumas perguntas:             |                           |
|  1. A alcada e por valor ou por tipo?        |  [v] PEs (1)              |
|                                              |    + MT100LOK             |
|  User: Por valor, acima de 10K precisa       |                           |
|  aprovacao do gerente                        |  [v] Fontes (1)           |
|                                              |    + XALCADA.prw          |
|  IA: Pra isso voce vai precisar de:          |                           |
|  - Campo A1_XALCAD na SA1 (valor limite)     |  [ ] Tabelas (0)          |
|  - PE MT100LOK pra validar na gravacao       |                           |
|  - Fonte customizado pra tela de aprovacao   |                           |
|  Quer que eu detalhe algum?                  |                           |
|                                              |                           |
|  [____________________________] [Enviar]     |  [Gerar Projeto]          |
+----------------------------------------------+---------------------------+
```

### Chat (lado esquerdo)
- Conversacional, limpo, so texto
- Detalhes tecnicos so se o usuario pedir
- Streaming SSE (resposta aparece em tempo real)
- Input na parte inferior

### Painel de Artefatos (lado direito)
- **NAO e contexto de busca** — e o que o projeto VAI criar/alterar
- Categorias colapsiveis: Campos, PEs, Fontes, Tabelas, Gatilhos
- Cada item mostra: nome, tabela, status (novo/alterar)
- Itens aparecem conforme a conversa evolui (a IA adiciona)
- Botao "Gerar Projeto" fixo no rodape do painel

### Menu Principal
- Label: "Peca ao Analista"
- Icone: `pi pi-user`
- Posicao: entre Dashboard e Base Padrao

## Ferramentas Internas (tools silenciosas)

A IA usa essas ferramentas nos bastidores — o usuario so ve o resultado filtrado.

| Tool | O que faz | Quando usa |
|---|---|---|
| `analise-impacto` | Fontes que escrevem na tabela, risco | Sempre que envolve campo/tabela |
| `padrao-cruzamento` | PEs existentes, rotinas padrao | Quando precisa saber o que ja existe |
| `funcao_resumir` | Gera resumo de funcao | Fonte relevante sem resumo |
| `enriquecer` | Gera overview de fonte | Fonte relevante sem overview |
| `deep_field_analysis` | Campos, validacoes, gatilhos | Contexto tecnico da tabela |
| `context_for_module` | Visao geral do modulo | Entender escopo do modulo |
| `vectorstore.search` | Busca semantica em fontes | Achar fontes por contexto |

### Filtro de Bom Senso

- **Inclui**: fontes que ESCREVEM na tabela, integracoes, PEs, gatilhos, validacoes
- **Exclui**: relatorios (so leitura), fontes que so consultam, menus de navegacao
- **Regra**: se `write_tables` nao contem a tabela em questao -> descarta
- **Overviews**: gera silenciosamente se fonte relevante nao tem, sem perguntar

## Output: Documentos

### 1. Projeto Gerencial (1 MD)
Para apresentar ao gestor/cliente:
- Resumo executivo (o que, porque, para quem)
- Escopo (itens que serao criados/alterados)
- Fluxo macro (Mermaid)
- Estimativa de esforco
- Riscos e pontos de atencao

### 2. Documentos Tecnicos (N MDs)
Um por entregavel, para o desenvolvedor:
- **Spec de campo**: nome, tipo, tamanho, validacao, trigger, tabela, inicializador
- **Spec de tabela nova**: campos, indices, relacionamentos, modo de acesso
- **Spec de PE**: qual PE usar, PARAMIXB esperado, logica, retorno
- **Spec de fonte**: objetivo, funcoes, tabelas leitura/escrita, fluxo Mermaid
- Cada doc e autonomo (pode ser entregue ao dev separadamente)

## Dados (SQLite)

### Tabela: `analista_projetos`
```sql
CREATE TABLE analista_projetos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL,
  descricao TEXT,
  status TEXT DEFAULT 'rascunho',  -- rascunho | em_andamento | concluido
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);
```

### Tabela: `analista_mensagens`
```sql
CREATE TABLE analista_mensagens (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  projeto_id INTEGER NOT NULL REFERENCES analista_projetos(id),
  role TEXT NOT NULL,        -- user | assistant | tool
  content TEXT NOT NULL,
  tool_data TEXT,            -- JSON: artefatos encontrados/criados nessa msg
  created_at TEXT DEFAULT (datetime('now'))
);
```

### Tabela: `analista_artefatos`
```sql
CREATE TABLE analista_artefatos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  projeto_id INTEGER NOT NULL REFERENCES analista_projetos(id),
  tipo TEXT NOT NULL,        -- campo | tabela | pe | fonte | gatilho
  nome TEXT NOT NULL,        -- ex: A1_XALCAD, MT100LOK, XALCADA.prw
  tabela TEXT,               -- tabela relacionada (SA1, SC5)
  acao TEXT DEFAULT 'criar', -- criar | alterar
  spec TEXT,                 -- JSON com detalhes tecnicos
  created_at TEXT DEFAULT (datetime('now'))
);
```

### Tabela: `analista_documentos`
```sql
CREATE TABLE analista_documentos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  projeto_id INTEGER NOT NULL REFERENCES analista_projetos(id),
  tipo TEXT NOT NULL,        -- gerencial | tecnico
  titulo TEXT NOT NULL,
  conteudo TEXT NOT NULL,    -- markdown gerado
  created_at TEXT DEFAULT (datetime('now'))
);
```

## Arquitetura Backend

### Novo router: `backend/routers/analista.py`
- `GET /api/analista/projetos` — lista projetos
- `POST /api/analista/projetos` — cria projeto
- `PUT /api/analista/projetos/{id}` — atualiza nome/status
- `DELETE /api/analista/projetos/{id}` — remove projeto
- `GET /api/analista/projetos/{id}/mensagens` — historico
- `POST /api/analista/projetos/{id}/chat` — envia mensagem (SSE streaming)
- `GET /api/analista/projetos/{id}/artefatos` — lista artefatos
- `POST /api/analista/projetos/{id}/gerar` — gera documentos do projeto
- `GET /api/analista/projetos/{id}/documentos` — lista docs gerados
- `GET /api/analista/projetos/{id}/documentos/{doc_id}/download` — download MD

### Logica do Chat (fluxo interno)
```
Mensagem do usuario
        |
classify() — detecta intencao e entidades
        |
Fase da conversa? (conta mensagens)
  < 4 msgs: modo investigativo (faz perguntas)
  >= 4 msgs: modo propositivo (sugere solucao)
        |
Busca silenciosa no banco:
  1. Tabelas mencionadas -> deep_field_analysis()
  2. Fontes que escrevem -> filtra so write_tables
  3. PEs na rotina -> padrao_cruzamento()
  4. Fontes sem overview -> enriquecer() silencioso
  5. Busca semantica -> vectorstore.search()
        |
Monta contexto filtrado (max ~8K tokens)
  - So dados relevantes ao escopo
  - Exclui relatorios/leitura
        |
LLM gera resposta + artefatos sugeridos
  - Resposta: texto conversacional
  - Artefatos: JSON com itens pro painel
        |
Salva mensagem + atualiza artefatos
Retorna via SSE stream
```

### System Prompt do Analista
```
Voce e um analista tecnico senior de Protheus.

COMPORTAMENTO:
- Seja direto e objetivo, sem enrolacao
- Faca 2-4 perguntas de negocio antes de sugerir solucao
- Quando sugerir, explique o "que" mas so o "porque" se pedirem
- Use o contexto do banco para embasar sugestoes
- Filtre: so traga o que impacta diretamente o escopo

CONTEXTO DISPONIVEL:
{contexto_filtrado}

ARTEFATOS DO PROJETO ATE AGORA:
{artefatos_atuais}

FORMATO DE RESPOSTA:
Responda em texto conversacional limpo.
Se sugerir novos artefatos, inclua ao final:
###ARTEFATOS###
[{"tipo": "campo", "nome": "A1_XALCAD", "tabela": "SA1", "acao": "criar"}]
```

## Reuso de Codigo Existente

### Backend (funcoes internas reutilizadas)
- `_padrao_cruzamento_fonte()` — cruzamento com padrao
- `analise_impacto()` — impacto de campos (adaptar para chamada interna)
- `funcao_resumir()` — resumo de funcoes
- `enriquecer()` — overview de fontes
- `KnowledgeService.build_deep_field_analysis()` — analise de campos
- `KnowledgeService.build_context_for_module()` — contexto do modulo
- `VectorStore.search()` — busca semantica
- `LLMService.classify()` — classificacao de intencao
- `LLMService._call()` e `_call_stream()` — chamada LLM

### Frontend (componentes reutilizados)
- PrimeVue: Card, Tag, Button, InputText, Badge, Panel, ScrollPanel
- Pattern de streaming SSE do ChatView existente
- parseResumo/parseResumoIA helpers do ExplorerView

### Nova View: `frontend/src/views/AnalistaView.vue`
- Componente unico com dois modos:
  - Modo lista (tela inicial com cards)
  - Modo projeto (chat + painel artefatos)
