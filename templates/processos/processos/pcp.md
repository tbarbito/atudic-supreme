# PCP — Processo Padrão Protheus

## Visão Geral
O módulo PCP (SIGAPCP) gerencia planejamento e controle da produção: ordens de produção, estrutura de produtos, necessidades de materiais (MRP) e apontamentos.

## Fluxo Padrão
1. Cadastro de Estrutura de Produto (MATA200 → SG1)
2. Previsão de Vendas / Plano Mestre
3. MRP — Cálculo de necessidades (MATA710)
4. Geração de Ordens de Produção (MATA650 → SC2)
5. Apontamento de Produção (MATA250 → SD3)
6. Encerramento de OP

## Tabelas Principais
- SC2 — Ordens de produção
- SG1 — Estrutura de produto
- SG2 — Roteiros de operação
- SD4 — Empenhos
- SHB — Operações da OP

## Rotinas Principais
- MATA200 — Estrutura de produto
- MATA630 — Ordens de produção
- MATA650 — Abertura de OP
- MATA680 — Apontamento de produção
- MATA710 — MRP

## Pontos de Entrada Comuns
- MT650GRV — Gravação da OP
- MT680GRV — Gravação do apontamento
