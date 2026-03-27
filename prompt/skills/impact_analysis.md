---
name: impact_analysis
description: Analise de impacto de alteracoes em campos, tabelas e fontes Protheus
intents: [field_change_request, table_info, source_analysis]
keywords: [impacto, alterar, criar campo, remover, modificar, risco, afeta, quebra, dependencia]
priority: 9
specialist: campo_agent
always_load: false
---

# Analise de Impacto

## Quando Usar

Sempre que o usuario quiser:
- Criar, alterar ou remover um campo
- Modificar estrutura de tabela
- Avaliar risco de mudanca
- Saber o que sera afetado por uma alteracao

## Protocolo

1. **Primeiro**: use `analyze_impact` com a tabela (e campo se especificado)
2. **Analise o resultado**: verifique fontes_leitura, fontes_escrita, gatilhos, vinculos
3. **Classifique o risco**:
   - BAIXO: < 3 fontes escrita, 0 gatilhos
   - MEDIO: 3-5 fontes escrita ou 1-3 gatilhos
   - ALTO: > 5 fontes escrita ou > 3 gatilhos ou integrações (MsExecAuto)
4. **Reporte**: liste todos os componentes afetados com detalhes

## Formato de Resposta

Sempre inclua:
- Quantos fontes leem e escrevem na tabela/campo
- Quais gatilhos serao afetados
- Se ha integrações (MsExecAuto, WebService)
- Nivel de risco com justificativa
- Lista de artefatos que precisam ser alterados
