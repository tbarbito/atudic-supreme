# Estoque/Custos — Processo Padrão Protheus

## Visão Geral
O módulo de Estoque/Custos (SIGAEST) controla movimentações de materiais, saldos, inventário e apuração de custos.

## Fluxo Padrão
1. Cadastro de Produtos (MATA010 → SB1)
2. Movimentações Internas (MATA240/MATA241 → SD3)
3. Documento de Entrada (atualizações em SB2/SD1)
4. Inventário (MATA330 → SB7)
5. Apuração de Custos (MATA330)

## Tabelas Principais
- SB1 — Produtos
- SB2 — Saldos em estoque (por armazém)
- SB5 — Dados complementares de produtos
- SD1 — Itens de NF de entrada
- SD3 — Movimentações internas

## Rotinas Principais
- MATA010 — Cadastro de produtos
- MATA240 — Requisição/Devolução interna
- MATA241 — Produção interna
- MATA250 — Transferência entre armazéns
- MATA260 — Inventário

## Pontos de Entrada Comuns
- MT010GRV — Gravação do cadastro de produto
- MT240GRV — Gravação de movimentação
