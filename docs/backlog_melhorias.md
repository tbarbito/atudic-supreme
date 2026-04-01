# Backlog de Melhorias — ExtraiRPO

## Pendentes

### 1. CRUD PEs na Base Padrão
- [x] Botão Excluir (remove PE errado do catálogo)
- [x] Botão Editar (modal pra corrigir módulo, rotina, objetivo)
- [x] Botão Pesquisar/Atualizar (Playwright + IA pesquisa e atualiza)
- [x] Row expansion mostrando PARAMIXB e retorno
- [x] TDN Scraper com Playwright (busca página, extrai PARAMIXB)
- **Status:** Concluído

### 8. Anotar, Exportar, Cruzar com Padrão
- [x] Anotar: substitui Enriquecer, caderno do consultor com tags
- [ ] Exportar: documento estruturado com fluxo Mermaid + impactos
- [ ] Cruzar com Padrão: nova aba no detalhe com rotinas, PEs, comparativo
- **Status:** Em andamento

### 9. WebService/Class detection
- [x] Parser detecta WSMETHOD, WSSTRUCT, WSSERVICE, METHOD...CLASS
- [x] source_type: webservice/class/user_function/etc
- [x] WS structures mostradas no detalhe do fonte
- [x] Re-ingestão preservando resumos (+242 funções novas)
- **Status:** Concluído

### 10. Dashboard Executivo
- [x] Cards grandes com métricas
- [x] Top 10 Mais Customizadas + Top 10 Maiores
- [x] Top 10 Interação de Fontes (leitura/escrita)
- [x] Módulos com barras
- [x] Cobertura de documentação
- [x] Score com legenda
- **Status:** Concluído

### 11. Análise de Impacto
- [x] Seleciona campo + tipo alteração → identifica fontes em risco
- [x] Classificação: alto (integrações), médio, baixo
- [x] Exporta como markdown
- **Status:** Concluído

### 2. Explorer: Padrão vs Custom
- [ ] Dentro de cada categoria separar itens padrão dos custom
- [ ] Tabelas: badge [PADRÃO+CUSTOM], [SÓ CLIENTE]
- [ ] Menus: agrupar itens padrão vs custom
- [ ] PEs: padrão implementados vs custom

### 3. Explorer: Record Counts
- [ ] Integrar 923 record counts na árvore (badges com registros)
- [ ] Filtro Com/Sem dados funcional
- [ ] Score usando record counts

### 4. Explorer: Detalhe clicável
- [ ] Verificar se clicar tabela/fonte carrega detalhe
- [ ] Corrigir se não funcionar

### 5. Encoding menus
- [ ] Corrigir "Cota.Jes" → "Cotações"
- [ ] Revisar encoding de todos os nomes de menu no SQLite

### 6. Fase 1: Classificação automática
- [ ] IA barata classifica top 50 tabelas/fontes por score
- [ ] Propósito em 1 frase pra cada (eliminar "A verificar")
- [ ] Salvar no SQLite (tabela propositos)

### 7. Explorer: Menus cliente
- [ ] Mostrar 45K itens de menu do cliente agrupados por módulo
- [ ] Comparação visual: rotinas padrão vs custom
- [ ] 5709 rotinas exclusivas do cliente destacadas

## Concluídos

### Base Padrão
- [x] Template 14 seções
- [x] 6 módulos reestruturados
- [x] Pergunte ao Padrão (pesquisa TDN+Web)
- [x] Aba TDN (árvore JSON)
- [x] Aba Pontos de Entrada (456 PEs, filtro por módulo)

### Ingestão
- [x] Parsers SX corrigidos (SIX, SX3, SX7)
- [x] Fontes parseados (1987 arquivos, memory-safe)
- [x] Menus padrão + cliente
- [x] Record counts (923 tabelas)
- [x] SXs padrão (174K campos)
- [x] Diff padrão vs cliente (31K registros)
- [x] Vínculos (19K conexões)
- [x] PEs catalogados (456 confirmados)
- [x] Auto-catalogação PEs por LLM

### Explorer
- [x] Backend 7 endpoints
- [x] Frontend 3 colunas
- [x] Árvore: Módulo > [Tabelas, PEs, Menus, Fontes]
- [x] Módulos consolidados
- [x] Badges diff (+adicionados, ~alterados)

### Pipeline v3
- [x] 4 estágios dual-model
- [x] Primeiro doc gerado (fiscal.md)
