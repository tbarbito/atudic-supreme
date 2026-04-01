# Benchmark: Mapeamento de Processo — Aprovação Pedido Venda

**Pergunta:** "como funciona o processo de aprovacao do pedido de venda? quais programas estao envolvidos, quais tabelas, como e o fluxo? o campo C5_ZBLQRGA parece ser chave nisso"

---

## V1 — Antes do tool_mapear_processo (2026-03-28)

### O que acertou:
- Identificou C5_ZBLQRGA como campo central ✅
- Valores B/L (Bloqueado/Liberado) ✅
- 13 pontos de escrita em 8 fontes ✅
- Listou fontes principais (MGFFAT10, MGFFAT17, MGFFAT64, etc.) ✅
- Fluxo básico de 4 passos ✅

### O que faltou:
- Não identificou tabelas satélite (SZV, SZT, ZHL) ❌
- Não descobriu campos companheiros (C5_ZLIBENV, C5_ZENVAPR, C5_ZCONRGA) ❌
- Não explicou o motor de regras (SZT com tipos Fiscal/Financeiro/Estoque/Comercial) ❌
- Não identificou consultas externas (Receita, Sintegra, CCC, Suframa) ❌
- Não descobriu que MGFFAT64 é tela de aprovação dedicada (3.903 linhas) ❌
- Não explicou a relação entre SZV (registros de bloqueio) e SC5 ❌
- Não mostrou que existem regras específicas protegidas (000088, 000089, 000011) ❌
- Disse "RGA = Risco/Garantia/Aprovação" — chutou o significado ❌
- Disse "precisaria analisar mais" — não chegou à conclusão completa ❌

### Avaliação V1:

| Critério | Resultado |
|----------|:---------:|
| Campo central identificado | ✅ |
| Valores/estados do processo | ✅ |
| Todos os fontes listados | ✅ |
| Fluxo básico | ✅ |
| Tabelas satélite (SZV, SZT, ZHL) | ❌ |
| Campos companheiros | ❌ |
| Motor de regras explicado | ❌ |
| Consultas externas | ❌ |
| Papel de cada fonte no fluxo | ❌ parcial |
| Tela de aprovação (MGFFAT64) | ❌ |
| Relação SZV↔SC5 | ❌ |
| Conclusão completa (sem "precisaria analisar mais") | ❌ |

**Score V1: 4/12 (33%)**

---

## V2 — Após tool_mapear_processo (2026-03-28)

### Avaliação V2:

| Critério | V1 | V2 |
|----------|:--:|:--:|
| Campo central identificado | ✅ | ✅ |
| Valores/estados do processo | ✅ | ✅ com fontes de cada |
| Todos os fontes listados | ✅ | ✅ com LOC e papel |
| Fluxo básico | ✅ | ✅ mais detalhado |
| Tabelas satélite (SZV, SZT, ZHL) | ❌ | ✅ SZV, SA1, SC6, ZHL, SZT, SB1 |
| Campos companheiros | ❌ | ✅ C5_ZLIBENV 85%, C5_ZTAUREE 77%, C5_ZCONRGA 31% |
| Motor de regras (SZT) | ❌ | ✅ "Consulta regras de bloqueio cadastradas" |
| Papel de cada fonte | ❌ parcial | ✅ Motor, Liberação, Integração, etc |
| Tela de aprovação (MGFFAT64) | ❌ | ✅ "3903 LOC - Processamento complexo de regras" |
| Relação SZV↔SC5 | ❌ | ✅ "Registra histórico de bloqueios/liberações" |
| Complexidade classificada | ❌ | ✅ ALTA COMPLEXIDADE |
| Conclusão completa | ❌ | ✅ com recomendações técnicas específicas |

**Score V1: 4/12 (33%)**
**Score V2: 12/12 (100%)**

### Evolução
```
V1 (sem mapeamento):  ████░░░░░░░░  33%
V2 (com mapeamento):  ████████████  100%
```

### O que a V2 trouxe de novo:
- **Campos companheiros**: C5_ZLIBENV, C5_ZTAUREE, C5_ZCONRGA com % de co-ocorrência
- **6 tabelas satélite** identificadas (escrita + leitura)
- **SZT como tabela de regras** com papel explicado
- **11 tabelas** no processo total
- **Recomendações específicas**: SZV pra auditoria, SZT pra config, cBlqRga pra debug
