# Financeiro — Processo Padrão Protheus

## Visão Geral
O módulo Financeiro (SIGAFIN) gerencia contas a pagar, contas a receber, fluxo de caixa, conciliação bancária e movimentações financeiras.

## Fluxo Padrão — Contas a Receber
1. Geração de títulos (automática via faturamento ou manual - FINA040 → SE1)
2. Emissão de boletos / borderôs
3. Baixa de títulos (FINA070)
4. Compensação e conciliação

## Fluxo Padrão — Contas a Pagar
1. Inclusão de títulos (FINA050 → SE2)
2. Aprovação de pagamento
3. Baixa de títulos a pagar (FINA080)
4. Emissão de cheques / transferências

## Tabelas Principais
- SE1 — Títulos a receber
- SE2 — Títulos a pagar
- SE5 — Movimentação bancária
- SA6 — Bancos
- SEA — Cheques

## Rotinas Principais
- FINA040 — Contas a receber
- FINA050 — Contas a pagar
- FINA070 — Baixa de contas a receber
- FINA080 — Baixa de contas a pagar
- FINA100 — Borderô de pagamento

## Pontos de Entrada Comuns
- FA040GRV — Gravação título a receber
- FA050GRV — Gravação título a pagar
- FA070GRV — Gravação da baixa a receber
