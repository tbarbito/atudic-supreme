# Compras — Processo Padrão Protheus

## Visão Geral
O módulo de Compras (SIGACOM) gerencia todo o ciclo de aquisição de materiais e serviços, desde a solicitação até o recebimento.

## Fluxo Padrão
1. Solicitação de Compras (MATA110 → SC1)
2. Cotação de Preços (MATA103 → SC8)
3. Análise de Cotações / Mapa de Cotações
4. Pedido de Compras (MATA120 → SC7)
5. Aprovação de Compras (via alçadas SCR)
6. Documento de Entrada (MATA103A → SD1/SF1)
7. Classificação Fiscal

## Tabelas Principais
- SC1 — Solicitações de compra
- SC7 — Pedidos de compra
- SC8 — Cotações de compra
- SA2 — Fornecedores
- SCR — Alçadas de aprovação
- SD1 — Itens de NF de entrada
- SF1 — Notas fiscais de entrada

## Rotinas Principais
- MATA110 — Solicitação de compra
- MATA103 — Cotação de preço
- MATA120 — Pedido de compra
- MATA121 — Autorização de compra
- MATA140 — Documento de entrada

## Pontos de Entrada Comuns
- MT120GRV — Gravação do pedido de compra
- MT103BRW — Browse da cotação
- MT140LOK — Validação do documento de entrada
