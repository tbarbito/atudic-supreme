# Gestão de Pessoas — Processo Padrão Protheus

## Visão Geral
O módulo de Gestão de Pessoas (SIGAGPE) controla cadastro de funcionários, folha de pagamento, ponto, férias, rescisão e obrigações trabalhistas.

## Fluxo Padrão
1. Cadastro de Funcionário (GPEA010 → SRA)
2. Registro de Ponto / Frequência
3. Cálculo de Folha de Pagamento (GPEM020 → SRC/SRD)
4. Geração de Encargos (INSS, FGTS, IR)
5. Férias (GPEA020 → SRB)
6. Rescisão
7. Geração de obrigações (eSocial, SEFIP, RAIS, DIRF)

## Tabelas Principais
- SRA — Funcionários
- SRB — Férias
- SRC — Movimentos mensais (holerite)
- SRD — Acumulados anuais
- SRE — Histórico salarial

## Rotinas Principais
- GPEA010 — Cadastro de funcionários
- GPEA020 — Férias
- GPEM020 — Cálculo de folha
- GPEM040 — Rescisão

## Pontos de Entrada Comuns
- GPA010GRV — Gravação cadastro funcionário
- GPM020CAL — Cálculo de folha
