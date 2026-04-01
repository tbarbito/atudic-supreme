# ExtraiRPO
### Plataforma Inteligente de Gestão de Ambientes Protheus

---

## O Problema de Negócio

Empresas que utilizam TOTVS Protheus acumulam **milhares de customizações** ao longo dos anos. Quando precisam fazer alterações, migrar versões ou auditar o ambiente, enfrentam:

- **Semanas de análise manual** para entender o que foi customizado
- **Quebra de integrações** por alterações sem análise de impacto
- **Zero documentação** dos programas customizados
- **Dependência de pessoas** — quando o desenvolvedor sai, o conhecimento vai junto
- **Risco operacional** — ninguém sabe exatamente o que o sistema faz

---

## A Solução

O ExtraiRPO **automatiza a engenharia reversa** do ambiente Protheus do cliente em minutos.

```
         ANTES                              DEPOIS
┌──────────────────────┐         ┌──────────────────────┐
│ Semanas de análise   │         │ 3 segundos de carga  │
│ Planilhas manuais    │   →→→   │ Navegação interativa │
│ "Pergunta pro João"  │         │ Documentação por IA  │
│ Alterou e quebrou    │         │ Análise de impacto   │
└──────────────────────┘         └──────────────────────┘
```

---

## Resultados Concretos

### Velocidade

| Atividade | Método tradicional | Com ExtraiRPO |
|---|---|---|
| Mapear customizações do cliente | 2-4 semanas | **3 segundos** |
| Identificar impacto de uma alteração | 1-2 dias | **10 segundos** |
| Documentar um programa customizado | 4-8 horas | **2 minutos** |
| Comparar padrão vs cliente | Não era feito | **Automático** |
| Catalogar pontos de entrada | Manual, incompleto | **457 catalogados com IA** |

### Cobertura

| O que analisa | Volume |
|---|---|
| Campos do dicionário | **187.633** analisados |
| Programas customizados | **1.987** parseados |
| Funções documentáveis | **8.522** identificadas |
| Diferenças padrão × cliente | **31.768** detectadas |
| Menus e rotinas | **45.023** mapeados |
| Tabelas com dados reais | **923** monitoradas |

### Redução de Risco

- **Análise de impacto automática** — antes de alterar qualquer campo, o sistema identifica todos os programas e integrações que serão afetados
- **Classificação por risco** — integrações e webservices sinalizados em vermelho
- **Documentação incremental** — cada consulta enriquece a base de conhecimento

---

## Funcionalidades Principais

### 1. Explorer — Raio-X do Ambiente
Navegação visual por módulo com drill-down em tabelas, campos, índices, gatilhos, fontes e menus. Comparação instantânea com o Protheus padrão.

### 2. Análise de Impacto
Selecione um campo, defina a alteração pretendida, e receba instantaneamente a lista de todos os programas afetados — classificados por nível de risco.

### 3. Documentação por IA
Inteligência artificial analisa cada programa e gera documentação estruturada automaticamente — objetivo, funcionalidades, tabelas manipuladas, fluxo do processo.

### 4. Base de Conhecimento Padrão
Referência completa do Protheus padrão: módulos, rotinas, pontos de entrada, parâmetros. Pesquisa inteligente no TDN integrada.

### 5. Diff Padrão × Cliente
Comparação campo a campo entre o dicionário padrão e o do cliente. Identifica exatamente o que foi adicionado, alterado ou removido — sem margem para erro.

---

## Público-Alvo

| Perfil | Como usa |
|---|---|
| **Consultor Protheus** | Chega no cliente e em minutos entende todo o ambiente |
| **Desenvolvedor** | Antes de alterar, roda análise de impacto |
| **Gerente de Projetos** | Visão clara do escopo de customizações |
| **Auditor / Compliance** | Rastreabilidade completa das alterações |
| **Gestor de TI** | Elimina dependência de pessoas |

---

## Diferenciais Competitivos

**1. Velocidade** — De semanas para segundos. Ingestão de 187K campos em 3 segundos.

**2. Precisão** — Diff campo a campo contra o padrão. Não depende de flag X3_PROPRI.

**3. Inteligência** — IA documenta automaticamente e a base de conhecimento cresce com o uso.

**4. Análise de Risco** — Única ferramenta que identifica impacto em integrações antes da alteração.

**5. Portabilidade** — Banco SQLite de 107MB. Roda local, sem dependências de servidor.

---

## Modelo de Uso

### Opção 1: Ferramenta de Consultoria
O consultor usa o ExtraiRPO como ferramenta de trabalho. Carrega os dados do cliente, analisa, documenta, entrega.

### Opção 2: Produto para Clientes
Licenciar para clientes finais que querem ter visibilidade do próprio ambiente Protheus.

### Opção 3: Serviço de Análise
Oferecer como serviço: cliente envia os CSVs e fontes, recebe o relatório completo de análise.

---

## Investimento Realizado

| Item | Detalhe |
|---|---|
| Backend | 13 endpoints, 6 serviços, 2.000+ linhas Python |
| Frontend | 8 views, 15+ componentes PrimeVue |
| Parsers | 7 parsers de SX, parser de fontes, parser de menus |
| IA | Prompts estruturados, pipeline dual-model, TDN Scraper |
| Dados | 107MB de base SQLite com 15 tabelas analíticas |

---

## Próximos Passos

1. **Gerador de Projetos** — IA cruza padrão + cliente e gera especificação de desenvolvimento
2. **Dashboard Executivo** — métricas visuais do ambiente do cliente
3. **Multi-cliente** — comparar customizações entre diferentes clientes
4. **Exportação** — relatórios em PDF/Word para entregas formais
5. **SaaS** — versão cloud com upload de dados

---

## Demonstração

**Acesse:** `http://localhost:8741`

| Tela | O que mostra |
|---|---|
| `/explorer` | Navegação interativa — tabelas, fontes, diff, impacto |
| `/padrao` | Base padrão com PEs, TDN, pergunte ao padrão |
| `/cliente` | Documentação gerada do cliente |
| `/chat` | Chat consultor com contexto do cliente |

---

*ExtraiRPO — Transformando complexidade em clareza.*
