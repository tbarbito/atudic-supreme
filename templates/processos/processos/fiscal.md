# Fiscal — Processo Padrão Protheus

## Visão Geral
O módulo Fiscal (SIGAFIS) gerencia obrigações fiscais, escrituração de livros, apuração de impostos (ICMS, IPI, PIS, COFINS) e geração de arquivos magnéticos (SPED).

## Fluxo Padrão
1. Escrituração de NF de Entrada/Saída (automática)
2. Apuração de ICMS (MATA953 → SF3)
3. Apuração de IPI
4. Apuração de PIS/COFINS
5. Geração SPED Fiscal (SPEDFISCAL)
6. Geração SPED Contribuições

## Tabelas Principais
- SF3 — Livros fiscais
- SF4 — Tipos de entrada/saída (TES)
- SFT — Livros fiscais por item
- CDA — Apuração de ICMS
- CDH — Apuração de IPI

## Rotinas Principais
- MATA950 — Escrituração fiscal
- MATA953 — Apuração de ICMS
- SPEDFISCAL — Geração SPED Fiscal

## Pontos de Entrada Comuns
- MT950GRV — Gravação escrituração
- SPDFSGEN — Geração do SPED
