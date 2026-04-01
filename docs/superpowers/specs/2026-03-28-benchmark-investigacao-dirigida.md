# Benchmark — Investigação Dirigida vs Tools Antigas vs Graph

**Data:** 2026-03-28

## Pergunta de teste

"tenho uma rotina acho que de abate, tem um campo valor de desconto algo assim, o usuario tem alterado isso na tela e parece que nao salva pode verificar"

## Resultados

### Approach A — Tools antigas (como Analista faz hoje)
- **Tokens contexto:** ~6.975
- **Tempo LLM:** 40.1s
- **Qualidade:** Lista todos os 22 write-points com campos detalhados. Mas NÃO traz parâmetros, NÃO explica o que é bEmite, NÃO mostra filiais afetadas.
- **Resposta:** Boa no detalhe de campos, fraca no diagnóstico da causa raiz.

### Approach B — Graph traversal puro
- **Tokens contexto:** ~2.118
- **Tempo LLM:** 22.3s
- **Qualidade:** Traz ecossistema completo (512 nós), 66 parâmetros com valores, 143 campos. Mas NÃO detalha campos por operação, NÃO explica condições (bEmite).
- **Resposta:** Boa visão geral, listou todas as operações com condições, mas sem detalhe de campos gravados.

### Approach C — Graph + tool_operacoes_tabela (híbrido)
- **Tokens contexto:** ~3.015
- **Tempo LLM:** 18.5s
- **Qualidade:** Traz operações detalhadas + ecossistema. Identificou ZZM_VLDESC, 3 condições. MAS não investigou fundo nas condições (bEmite → parâmetros).
- **Resposta:** Melhor custo-benefício, mas falta investigação de condição.

### Approach D — Investigação Dirigida (A SER IMPLEMENTADO)
- **Tokens contexto estimado:** ~3.000-4.000
- **Expectativa:** Parte do campo ZZM_VLDESC, busca quem grava, rastreia condições (bEmite → MGF_TAE15A, MGF_TAE17), traz valores das filiais, explica exceção Rondônia. CIRÚRGICO.

## Resumo comparativo

| Approach | Tokens | Tempo | Parâmetros | Campos/op | Condições | Diagnóstico |
|----------|--------|-------|------------|-----------|-----------|-------------|
| A tools  | ~7.000 | 40s   | Não        | Sim       | Superficial | Parcial |
| B graph  | ~2.100 | 22s   | Sim (66)   | Não       | Sim (resumo) | Parcial |
| C híbrido| ~3.000 | 18s   | Sim (66)   | Sim       | Superficial | Parcial |
| D dirigido| ~3.500 | ~20s  | Sim (foco) | Sim (foco)| **Profundo** | **Completo** |

## O que D precisa trazer para essa pergunta

```
CAMPO: ZZM_VLDESC (Vl.Desconto, N, 14.2)
PROBLEMA: alteracao na tela nao persiste

OPERACOES QUE GRAVAM ZZM_VLDESC:
1. TAE15_GRV (MGFTAE15.PRW) — cond: bEmite
   bEmite = .T. quando filial NAO esta em MGF_TAE17
   MGF_TAE17 = "010005;010064;010068" (fornecedor emite NF)
   Se filial nessa lista → bEmite = .F. → NAO grava VLDESC
   Excecao: Rondonia (MGF_TAE15R = "RO") depende se PF ou PJ (MGFFIS36)

2. TAE15_GRV bloco NOT bEmite — grava ZZM_OBS, ZZM_VENCE (NAO grava VLDESC)

3. MGFTAE14 — inclusao, grava VLDESC so na criacao

ROTINA: MGFTAE15.PRW (Boletim de Abate)
```

## Resposta esperada do LLM

"Na filial 010005 (e 010064, 010068) o fornecedor emite a NF, então o sistema
não grava o desconto. Para filiais onde a empresa emite, o desconto é salvo
normalmente. Se for Rondônia, depende se o fornecedor é Pessoa Física ou Jurídica."
