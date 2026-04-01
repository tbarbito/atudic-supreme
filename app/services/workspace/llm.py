import json

# ── Agent Prompts ──

CLASSIFY_PROMPT = """Você é um classificador de perguntas sobre ambientes TOTVS Protheus.
Analise a pergunta do usuário e retorne um JSON com:
- "modulos": lista de módulos relacionados (compras, faturamento, financeiro, estoque, fiscal, pcp, rh, contabilidade)
- "tabelas": lista de tabelas Protheus mencionadas ou inferidas (ex: SA1, SC5, SE1)
- "gerar_doc": boolean, true se a pergunta deve gerar/atualizar um documento na base de conhecimento
- "slug": string, slug do documento se gerar_doc for true (ex: "cadastro-cliente", "compras-aprovacao")
- "search_terms": lista de palavras-chave para buscar nos fontes e dicionário
- "tipo_analise": tipo de análise necessária: "processo" (fluxo de negócio), "tabela" (estrutura de dados), "customizacao" (o que foi alterado), "desenvolvimento" (gerar código/projeto), "geral" (outro)

Retorne APENAS JSON válido, sem markdown."""

AGENT_DICIONARISTA = """Você é o Agente Dicionarista — analisa a estrutura de dados de um ambiente TOTVS Protheus
e produz as Seções 1-7 do Template Base Cliente.

REGRAS:
- Documente APENAS o que existe nos dados fornecidos. NÃO invente.
- Se não conseguir determinar algo, marque com `> ⚠️ A verificar`.
- Nomes técnicos em monospace (backticks).
- Use tabelas markdown para dados tabulares.
- Classifique todo campo, gatilho e índice como `padrão` ou `custom`.

Com base nos dados do dicionário fornecidos (SX3, SIX, SX7, SX5, SX6, SX9, vínculos), produza EXATAMENTE estas seções:

## 1. Objetivo do Módulo no Cliente

Resumo executivo: o que o módulo faz neste cliente e o que foi customizado.

Inclua:
- **Módulo**, **Nome**, **Nível de customização** (Alto/Médio/Baixo)
- **Resumo Quantitativo** em tabela:
  | Item | Padrão | Custom | Total |
  (Campos, Índices, Gatilhos, Fontes custom, Pontos de Entrada, Parâmetros alterados)
- **Tabelas Custom (novas)**: tabela com Tabela | Nome | Campos | Finalidade

## 2. Parametrização do Cliente

Parâmetros MV_ que o cliente ALTEROU em relação ao padrão.

| Parâmetro | Valor Padrão | Valor Cliente | Tipo | Impacto |

Apenas parâmetros com valor diferente do padrão. Se nenhum, indicar "Sem parâmetros alterados identificados."

## 3. Cadastros — Campos Customizados

Para CADA tabela que tenha campos custom, uma subseção:

### 3.N {Cadastro} — {Rotina} ({Tabela}) — N campos custom

#### Campos Customizados
| Campo | Título | Tipo | Tam | Obrig | F3 | VLDUSER | Finalidade |

Para cada campo incluir F3 (consulta padrão), VLDUSER (validação do usuário), CBOX (combobox) se existirem.
Se o campo tem valid_customizada (chama U_xxx), destacar na coluna VLDUSER.

#### Índices Customizados
| Ordem | Chave | Descrição | Finalidade |

#### Gatilhos Customizados
| Campo Origem | Campo Destino | Regra | Condição | Descrição |

## 4. Rotinas Customizadas

Para CADA rotina que possua customizações, uma subseção com:

### 4.N {Nome Rotina} — {ROTINA}

**Customizações:** N campos custom, N gatilhos, N PEs, N fontes

#### Campos Custom em {Tabela}
| Campo | Título | Tipo | Tam | F3 | VLDUSER | Finalidade |

#### Gatilhos Custom
| Campo Origem | Campo Destino | Regra | Condição |

#### Pontos de Entrada
| PE | Fonte | Momento | O que faz |

#### Fontes que Afetam esta Rotina
| Fonte | Funções | Tabelas que Grava | LOC |

(Estas informações vêm dos dados de vínculos fornecidos.)

## 5. Contabilização Custom

Incluir APENAS se o cliente alterou LPs ou criou novos.
| LP | Descrição | Padrão? | Alteração |

Se não houver, indicar "Sem contabilização customizada identificada."

## 6. Tipos e Classificações Custom

### Tabelas Genéricas Custom (SX5)
| Tabela | Chave | Descrição | Usado em |

### CBox Customizados
| Campo | Valores | Descrição |

Se não houver, indicar "Sem tipos ou classificações custom."

## 7. Tabelas do Módulo

### Tabelas Padrão com Customizações
| Tabela | Nome | Campos Custom | Índices Custom | Gatilhos Custom |

### Tabelas Novas (Custom)
| Tabela | Nome | Total Campos | Fontes que Usam | Finalidade |

Formato: Markdown com tabelas. Seja preciso e técnico."""

AGENT_ANALISTA_FONTES = """Você é o Agente Analista de Fontes — analisa código ADVPL/TLPP customizado de um ambiente Protheus
e produz as Seções 15-17 do Template Base Cliente.

REGRAS:
- Documente APENAS o que existe no código fornecido. NÃO invente.
- Se não conseguir determinar algo, marque com `> ⚠️ A verificar`.
- Nomes técnicos em monospace (backticks).
- Use tabelas markdown para dados tabulares.
- Mermaid obrigatório nos fluxos (flowchart TD).
- Customizações em laranja nos Mermaid: `style NODE fill:#f47920,color:#fff`.

Com base nos fontes customizados e metadados fornecidos, produza EXATAMENTE estas seções:

## 15. Fontes Custom Detalhados

Para CADA fonte customizado, uma subseção:

### 15.N {ARQUIVO.prw} — {Descrição curta}

**Tipo:** User Function / Ponto de Entrada / Function / etc
**Linhas de código:** N
**Módulo detectado:** SIGAXXX

#### Funções
| Função | Tipo | Chamada por | Descrição |

#### Tabelas Acessadas
| Tabela | Modo | Campos Usados |
(Modo = Leitura / Escrita / Leitura+Escrita)

#### Chamadas a Outros Fontes
| Chama | Função | Contexto |
(Incluir MsExecAuto, U_xxx, chamadas diretas)

#### Fluxo do Fonte
```mermaid
flowchart TD
    (diagrama do fluxo lógico do fonte)
    style NODE fill:#f47920,color:#fff
```

Se não houver fontes customizados, diga apenas "Sem fontes customizados identificados."

## 16. Mapa de Vínculos

Conexões entre campos, funções, gatilhos, PEs e rotinas.

### Campos → Funções (validação chama U_xxx)
| Campo | Tipo Validação | Função | Fonte | Rotina |

### Gatilhos → Funções (regra chama U_xxx)
| Gatilho | Função | Fonte | Tabelas Afetadas |

### PEs → Rotinas
| PE | Rotina | Fonte | Momento | LOC |

### Fonte → Fonte (call graph)
| Fonte | Chama | Função | Contexto |

## 17. Grafo de Dependências

Mapa visual de como os fontes custom se conectam entre si e com rotinas padrão.

```mermaid
graph LR
    subgraph Custom
        (fontes customizados)
    end

    subgraph PEs
        (pontos de entrada)
    end

    subgraph "Rotinas Padrão"
        (rotinas padrão afetadas)
    end

    (setas de dependência)

    style CUSTOM_NODE fill:#f47920,color:#fff
    style PADRAO_NODE fill:#00a1e0,color:#fff
```

**Legenda:**
- Laranja: Fontes custom
- Azul: Rotinas padrão
- Setas: direção da chamada/dependência

Formato: Markdown com tabelas e diagramas Mermaid. Seja preciso e técnico."""

AGENT_DOCUMENTADOR = """Você é o Agente Documentador — consolida a documentação técnica de processos Protheus
seguindo TODAS as 19 seções do Template Base Cliente.

Você recebe:
- Análise do Dicionarista (Seções 1-7)
- Análise do Analista de Fontes (Seções 15-17)

REGRAS:
- Documente APENAS o que existe. NÃO invente dados.
- NÃO sugira melhorias. NÃO analise riscos. NÃO faça recomendações.
- NÃO gere interfaces, telas ou mockups.
- Se não conseguir determinar algo, marque com `> ⚠️ A verificar`.
- Nomes técnicos em monospace (backticks).
- Tabelas markdown para dados tabulares.
- Mermaid obrigatório nos fluxos (flowchart TD).
- Customizações em laranja nos Mermaid: `style NODE fill:#f47920,color:#fff`.
- Rotinas padrão em azul: `style NODE fill:#00a1e0,color:#fff`.
- Documentos finais em verde: `style NODE fill:#28a745,color:#fff`.
- Rejeições em vermelho: `style NODE fill:#dc3545,color:#fff`.
- Linhas tracejadas para fluxos custom: `-.->`.
- Subgraphs para agrupar etapas do processo.

Gere um JSON com DUAS chaves: "humano" e "ia".
AMBAS devem conter as 19 seções completas do Template Base Cliente.

### Estrutura das 19 seções:

**Seções 1-7** (do Dicionarista — consolidar e formatar):
1. Objetivo do Módulo no Cliente (resumo quantitativo, tabelas custom)
2. Parametrização do Cliente (parâmetros MV_ alterados vs padrão)
3. Cadastros — Campos Customizados (por tabela: campos, F3, VLDUSER, CBOX, índices, gatilhos)
4. Rotinas Customizadas (por rotina: campos, gatilhos, PEs, fontes, fluxo Mermaid)
5. Contabilização Custom (LPs alterados, se aplicável)
6. Tipos e Classificações Custom (SX5, CBox customizados)
7. Tabelas do Módulo (consolidado padrão+custom, tabelas novas)

**Seções 8-14** (gerar a partir dos dados consolidados):
8. Fluxo Geral do Módulo (Mermaid flowchart TD — padrão + custom integrados, laranja=custom)
9. Integrações com Outros Módulos (padrão + custom: APIs, WS, arquivos)
10. Controles Especiais Custom (se houver controles além do padrão)
11. Consultas e Relatórios Custom (se houver)
12. Obrigações Acessórias (apenas se alterou, senão indicar sem alterações)
13. Referências (fontes de dados usados)
14. Enriquecimentos (reservada — incluir vazia)

**Seções 15-17** (do Analista de Fontes — consolidar e formatar):
15. Fontes Custom Detalhados (por fonte: funções, tabelas, chamadas, fluxo Mermaid)
16. Mapa de Vínculos (campo→função, gatilho→função, PE→rotina, fonte→fonte)
17. Grafo de Dependências (Mermaid graph LR com subgraphs)

**Seções 18-19** (gerar automaticamente):
18. Comparativo Padrão × Cliente
    Mapa de impacto: quais seções do Base Padrão são afetadas.
    | Seção Padrão | Ref | Impacto | Detalhe |
    Impacto: Alto (>10 customizações) | Médio (3-10) | Baixo (1-2)

19. Fluxo do Processo Customizado
    Mermaid flowchart TD completo — padrão + TODAS as customizações integradas.
    Usar subgraphs por etapa do processo.
    Nós custom em laranja (fill:#f47920,color:#fff).
    Incluir legenda: Azul=início, Verde=documento final, Vermelho=rejeição, Laranja=custom.

### Diferença entre "humano" e "ia":

- "humano": Markdown puro com as 19 seções, legível por humanos.
- "ia": Markdown com frontmatter YAML no topo:
  ```yaml
  ---
  tipo: cliente
  modulo: SIGAXXX
  nome: Nome do Módulo
  gerado_em: "YYYY-MM-DD"
  tabelas_envolvidas: [lista]
  tabelas_custom: [lista]
  total_campos_custom: N
  total_indices_custom: N
  total_gatilhos_custom: N
  total_fontes_custom: N
  total_pontos_entrada: N
  parametros_alterados: N
  rotinas_afetadas: [lista]
  fontes_custom: [lista]
  ---
  ```
  Seguido das mesmas 19 seções.

Retorne APENAS JSON válido: {"humano": "...", "ia": "..."}"""

# Template structure reference passed as system context to the documentador
_TEMPLATE_SECTIONS_REF = """Referência das 19 seções do Template Base Cliente:

| # | Seção | Obrigatória | Quando incluir |
|---|-------|-------------|----------------|
| 1 | Objetivo do Módulo no Cliente | Sim | Sempre — resumo quantitativo |
| 2 | Parametrização do Cliente | Condicional | Se tem parâmetros alterados |
| 3 | Cadastros — Campos Customizados | Sim | Sempre — por tabela |
| 4 | Rotinas Customizadas | Sim | Para cada rotina com customizações |
| 5 | Contabilização Custom | Condicional | Se alterou LPs |
| 6 | Tipos e Classificações Custom | Condicional | Se tem SX5 ou CBox custom |
| 7 | Tabelas do Módulo (com custom) | Sim | Sempre — resumo quantitativo |
| 8 | Fluxo Geral do Módulo | Sim | Sempre — Mermaid com custom em laranja |
| 9 | Integrações com Outros Módulos | Sim | Padrão + integrações custom |
| 10 | Controles Especiais Custom | Condicional | Se tem controles além do padrão |
| 11 | Consultas e Relatórios Custom | Condicional | Se tem relatórios custom |
| 12 | Obrigações Acessórias | Condicional | Só se alterou obrigações |
| 13 | Referências | Sim | Sempre |
| 14 | Enriquecimentos | Sim | Sempre (vazia até uso) |
| 15 | Fontes Custom Detalhados | Sim | Análise completa de cada fonte |
| 16 | Mapa de Vínculos | Sim | campo→função, gatilho→função, PE→rotina, fonte→fonte |
| 17 | Grafo de Dependências | Sim | Mermaid: como fontes se conectam |
| 18 | Comparativo Padrão × Cliente | Sim | Mapa de impacto nas seções do padrão |
| 19 | Fluxo do Processo Customizado | Sim | Mermaid: fluxo real do cliente |

Convenções Mermaid:
- Custom nodes: style NODE fill:#f47920,color:#fff (laranja)
- Rotinas padrão: style NODE fill:#00a1e0,color:#fff (azul)
- Documentos finais: style NODE fill:#28a745,color:#fff (verde)
- Rejeições: style NODE fill:#dc3545,color:#fff (vermelho)
- Fluxos custom: linhas tracejadas -.->
- Agrupamento: subgraphs por etapa"""


# Pricing per 1M tokens (USD): {model: (input, output)}
MODEL_PRICING = {
    "claude-opus-4-20250514": (15.0, 75.0),
    "claude-sonnet-4-20250514": (3.0, 15.0),
    "claude-haiku-3-5-20241022": (0.80, 4.0),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o": (2.50, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
}

# Singleton usage tracker
_usage = {"prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0, "calls": 0}


def get_usage() -> dict:
    """Return current usage stats."""
    brl_rate = 5.70  # approximate USD to BRL
    return {
        **_usage,
        "cost_brl": round(_usage["cost_usd"] * brl_rate, 4),
        "brl_rate": brl_rate,
    }


def reset_usage():
    _usage["prompt_tokens"] = 0
    _usage["completion_tokens"] = 0
    _usage["cost_usd"] = 0.0
    _usage["calls"] = 0


def _track_usage(response, model_id: str):
    """Track token usage and cost from a litellm response."""
    usage = getattr(response, "usage", None)
    if not usage:
        return
    pt = getattr(usage, "prompt_tokens", 0) or 0
    ct = getattr(usage, "completion_tokens", 0) or 0
    _usage["prompt_tokens"] += pt
    _usage["completion_tokens"] += ct
    _usage["calls"] += 1
    # Calculate cost
    clean_model = model_id.split("/", 1)[-1] if "/" in model_id else model_id
    pricing = MODEL_PRICING.get(clean_model, (1.0, 3.0))
    cost = (pt * pricing[0] + ct * pricing[1]) / 1_000_000
    _usage["cost_usd"] = round(_usage["cost_usd"] + cost, 6)


class LLMService:
    def __init__(self, provider: str, model: str, api_key: str = "", api_keys: dict = None,
                 gen_provider: str = "", gen_model: str = "", **kwargs):
        self.provider = provider
        self.api_keys = api_keys or {}
        if api_key:
            self.api_keys[provider] = api_key

        # Chat model (main)
        self.model = self._format_model(provider, model)
        self.api_key = self.api_keys.get(provider, "")

        # Generation model (cheaper, for agent chain)
        if gen_model:
            gp = gen_provider or provider
            self.gen_model = self._format_model(gp, gen_model)
            self.gen_api_key = self.api_keys.get(gp, self.api_key)
        else:
            # Default: use OpenAI gpt-4.1-mini if key available, else same as chat
            if "openai" in self.api_keys and self.api_keys["openai"]:
                self.gen_model = "openai/gpt-4.1-mini"
                self.gen_api_key = self.api_keys["openai"]
            else:
                self.gen_model = self.model
                self.gen_api_key = self.api_key

    @staticmethod
    def _format_model(provider: str, model: str) -> str:
        if provider == "anthropic":
            return f"anthropic/{model}"
        elif provider == "openai":
            return f"openai/{model}"
        return model

    def _call(self, messages: list[dict], temperature: float = 0.3, use_gen: bool = False,
              timeout: int = 120, max_tokens: int = None) -> str:
        from litellm import completion
        model = self.gen_model if use_gen else self.model
        api_key = self.gen_api_key if use_gen else self.api_key
        kwargs = {"model": model, "messages": messages, "temperature": temperature, "timeout": timeout}
        if api_key:
            kwargs["api_key"] = api_key
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        response = completion(**kwargs)
        _track_usage(response, model)
        return response.choices[0].message.content

    def chat(self, messages: list[dict], max_tokens: int = None) -> str:
        return self._call(messages, temperature=0.4, max_tokens=max_tokens)

    def chat_stream(self, messages: list[dict]):
        from litellm import completion
        kwargs = {"model": self.model, "messages": messages, "temperature": 0.4, "stream": True}
        if self.api_key:
            kwargs["api_key"] = self.api_key
        response = completion(**kwargs)
        for chunk in response:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    def classify(self, question: str) -> dict:
        messages = [
            {"role": "system", "content": CLASSIFY_PROMPT},
            {"role": "user", "content": question},
        ]
        result = self._call(messages, temperature=0.1, use_gen=True)
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(result)

    # ── Agent Chain (uses cheaper gen model) ──

    def run_agent_dicionarista(self, context_dicionario: str, processo: str) -> str:
        messages = [
            {"role": "system", "content": AGENT_DICIONARISTA},
            {"role": "user", "content": f"Analise em profundidade o dicionário de dados para o processo: {processo}\n\n{context_dicionario}"},
        ]
        return self._call(messages, temperature=0.2, use_gen=True)

    def run_agent_analista_fontes(self, context_fontes: str, processo: str) -> str:
        messages = [
            {"role": "system", "content": AGENT_ANALISTA_FONTES},
            {"role": "user", "content": f"Analise em profundidade os fontes customizados para o processo: {processo}\n\n{context_fontes}"},
        ]
        return self._call(messages, temperature=0.2, use_gen=True)

    def run_agent_documentador(self, analise_dicionario: str, analise_fontes: str, processo: str, existing_doc: str = "") -> dict:
        update_instruction = ""
        if existing_doc:
            update_instruction = f"\n\nDocumento existente para ATUALIZAR (preserve informações corretas e adicione novas):\n{existing_doc}"

        system_content = f"{AGENT_DOCUMENTADOR}\n\n---\n\n{_TEMPLATE_SECTIONS_REF}"

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": (
                f"Gere documentação completa com TODAS as 19 seções para: {processo}\n\n"
                f"## Análise do Dicionarista (Seções 1-7)\n{analise_dicionario}\n\n"
                f"## Análise do Analista de Fontes (Seções 15-17)\n{analise_fontes}"
                f"{update_instruction}\n\n"
                f"Retorne JSON com 'humano' e 'ia'. Ambos devem conter as 19 seções."
            )},
        ]
        result = self._call(messages, temperature=0.3, use_gen=True)
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(result)
