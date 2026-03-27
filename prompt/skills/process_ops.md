---
name: process_ops
description: Mapeamento de processos de negocio Protheus — tabelas, campos, fluxos entre modulos
intents: [table_info, general]
keywords: [processo, process, fluxo, flow, modulo, SIGAFIN, SIGACOM, SIGAFAT, SIGAMNT, SIGAFIS, SIGAEST, SIGACTB, compra, venda, faturamento, financeiro, fiscal, estoque, mapa, diagrama]
priority: 65
max_tokens: 500
specialist: "knowledge"
---

## PROCESSOS DE NEGOCIO PROTHEUS

### O que sao processos no AtuDIC
Mapeamento visual de como os dados fluem entre tabelas e modulos do Protheus.
Cada processo tem: tabelas vinculadas, campos-chave e fluxos para outros processos.

### Modulos Protheus
| Sigla | Modulo | Exemplos de processo |
|-------|--------|---------------------|
| SIGAFIN | Financeiro | Contas a pagar, contas a receber, fluxo de caixa |
| SIGACOM | Compras | Pedido de compra, cotacao, solicitacao |
| SIGAFAT | Faturamento | Pedido de venda, nota fiscal saida, PDV |
| SIGAEST | Estoque | Movimentacao, inventario, saldos |
| SIGAFIS | Fiscal | SPED, livros fiscais, obrigacoes |
| SIGAMNT | Manutencao | Ordens de servico, ativos |
| SIGACTB | Contabilidade | Lancamentos, balancetes |
| SIGAGPE | Gestao de Pessoas | Folha, ferias, beneficios |

### Tabelas mais comuns por processo

**Compras:** SC7 (pedido) → SD1 (itens NF entrada) → SF1 (cabecalho NF) → SE2 (contas a pagar)
**Vendas:** SC5 (pedido) → SC6 (itens) → SD2 (itens NF saida) → SF2 (cabecalho NF) → SE1 (contas a receber)
**Estoque:** SD1/SD2 → SB2 (saldos) → SB1 (produtos)
**Fiscal:** SF1/SF2 → SF3 (livros fiscais) → SPED

### Campos-chave de ligacao entre tabelas
- `C5_NUM` (SC5) → `C6_NUM` (SC6): pedido de venda cab → itens
- `C7_NUM` (SC7) → `D1_DOC` (SD1): pedido compra → NF entrada
- `F1_DOC` (SF1) → `D1_DOC` (SD1): NF entrada cab → itens
- `F2_DOC` (SF2) → `D2_DOC` (SD2): NF saida cab → itens
- `E1_NUM` (SE1) → `F2_DOC` (SF2): titulo a receber → NF saida

### Quando orientar sobre processos
- "como funciona o fluxo de compras?" → explicar SC7→SD1→SF1→SE2
- "quais tabelas do faturamento?" → SC5, SC6, SD2, SF2, SE1
- "como o pedido vira nota?" → fluxo SC5→SC6→MATA461→SD2/SF2
- "mapeie o processo X" → sugerir usar modulo Processos > Novo Processo

### Regras
- Ao explicar fluxos, sempre citar as tabelas envolvidas com alias (SC5, SF1, etc.)
- Citar campos-chave que ligam as tabelas
- Referenciar o modulo "Processos da Empresa" do AtuDIC para mapeamento visual
- Nunca inventar fluxos — basear-se nos processos cadastrados ou no conhecimento padrao Protheus
