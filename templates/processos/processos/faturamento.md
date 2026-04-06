# Faturamento — Processo Padrão Protheus

## Visão Geral
O módulo de Faturamento (SIGAFAT) controla o ciclo de vendas desde o pedido até a emissão da nota fiscal.

## Fluxo Padrão
1. Pedido de Venda (MATA410 → SC5/SC6)
2. Liberação do Pedido (MATA411 → campo C5_LIBEROK)
3. Preparação de NF (MATA460A)
4. Faturamento / Nota Fiscal de Saída (MATA461 → SF2/SD2)
5. Transmissão NF-e (SPEDNFE)
6. Geração de títulos a receber (SE1)

## Tabelas Principais
- SC5 — Cabeçalho pedido de venda
- SC6 — Itens do pedido de venda
- SF2 — Notas fiscais de saída
- SD2 — Itens da NF de saída
- SA1 — Clientes
- SE1 — Títulos a receber

## Rotinas Principais
- MATA410 — Pedido de venda
- MATA411 — Liberação de pedidos
- MATA460 — Preparação de NF
- MATA461 — Faturamento / Geração de NF

## Pontos de Entrada Comuns
- MT410GRV — Gravação do pedido de venda
- MT410BRW — Browse do pedido
- MTA461LNK — Linkagem NF com pedido
- A410STTS — Validação de status do pedido
