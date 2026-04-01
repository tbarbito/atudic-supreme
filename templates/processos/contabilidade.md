# Contabilidade — Processo Padrão Protheus

## Visão Geral
O módulo de Contabilidade (SIGACTB) gerencia plano de contas, lançamentos contábeis, apurações, balancetes e demonstrações financeiras.

## Fluxo Padrão
1. Cadastro de Plano de Contas (CTBA010 → CT1)
2. Lançamentos Contábeis (CTBA102 → CT2)
3. Lançamentos automáticos (via movimentações de outros módulos)
4. Apuração de resultados
5. Balancete / Razão (CTBA020)
6. Demonstrações (DRE, Balanço)

## Tabelas Principais
- CT1 — Plano de contas
- CT2 — Lançamentos contábeis
- CT5 — Lançamentos padrão
- CTS — Saldos contábeis
- CVD — Visões gerenciais

## Rotinas Principais
- CTBA010 — Plano de contas
- CTBA020 — Balancete/Razão
- CTBA102 — Lançamentos contábeis
- CTBA105 — Apuração de resultado

## Pontos de Entrada Comuns
- CT102GRV — Gravação de lançamento
- CT020IMP — Impressão balancete
