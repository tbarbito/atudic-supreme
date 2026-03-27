# Memória Procedural do Agente AtuDIC

> Protocolos e procedimentos operacionais para o ambiente Protheus.
> Cada seção descreve um procedimento passo-a-passo.

---

## Análise de Error.log

### Quando usar
Quando o AppServer apresenta erros recorrentes ou comportamento inesperado.

### Procedimento
1. Acessar módulo Observabilidade no AtuDIC
2. Verificar alertas ativos e severidade
3. Filtrar por categoria de erro (SSL, SQL, Lock, etc.)
4. Analisar recorrência — erros repetitivos indicam problema sistêmico
5. Consultar Base de Conhecimento para solução documentada
6. Se não houver artigo, escalar para análise manual
7. Registrar solução encontrada na Base de Conhecimento

### Dicas
- Erros de Thread Error no faturamento geralmente indicam excesso de usuários simultâneos
- Erros de TopConnect/SQL com "connection lost" podem indicar problema de rede ou DbAccess
- Erros de Lock persistentes sugerem processo travado — verificar usuários logados

---

## Aplicação de Patch (RPO)

### Quando usar
Quando há correção de fonte AdvPL a ser aplicada no ambiente.

### Procedimento
1. Verificar política de branch no Dev Workspace (branch → ambiente)
2. Compilar fonte no TDS ou via pipeline AtuDIC
3. Gerar patch .ptm com os fontes alterados
4. **DEV/TST:** aplicar diretamente
5. **HML:** aplicar e validar com usuário-chave
6. **PRD:** exigir aprovação + backup do RPO antes de aplicar
7. Após aplicação, reiniciar AppServer (graceful se possível)
8. Validar no console.log que o fonte novo foi carregado
9. Registrar no histórico de correções

### Riscos
- Nunca aplicar patch em PRD sem backup do RPO
- Sempre validar em HML antes de PRD
- Patches com alteração de SX3 (dicionário) exigem reinício completo

---

## Tombamento de Base

### Quando usar
Quando o ambiente HML/DEV precisa ser atualizado com dados de PRD.

### Procedimento
1. Confirmar que PRD **nunca** será destino
2. Parar serviços do ambiente destino (AppServer + DbAccess)
3. Fazer backup do banco destino (segurança)
4. Executar restore do backup de PRD no banco destino
5. Ajustar parâmetros do SX6 (empresa, CNPJ, etc.) para não confundir com PRD
6. Executar UPDDISTR se houver diferença de release
7. Reiniciar serviços
8. Validar acesso e dados

### Cuidados
- Sanitizar dados sensíveis se necessário (senhas, dados pessoais)
- Conferir se o RPO do destino é compatível com o release do banco copiado
- Atualizar variáveis de ambiente no AtuDIC (conexão BD pode mudar)

---

## Compilação de Fontes

### Procedimento via AtuDIC
1. Acessar Dev Workspace → Assistente de Compilação
2. Selecionar ambiente de destino
3. O sistema mostra diff entre FONTES_DIR e repositório
4. Selecionar fontes a compilar
5. Gerar arquivo compila.txt
6. Executar pipeline de compilação

### Procedimento via TDS
1. Conectar ao AppServer via TDS (SmartClient)
2. Selecionar ambiente
3. Adicionar fontes ao projeto
4. Compilar (F9 ou menu Build)
5. Verificar console para erros de compilação
6. Testar funcionalidade alterada

### Dicas
- Arquivos .prw/.tlpp devem estar em encoding ANSI (cp1252)
- Erros de "User Function not found" indicam que o fonte não foi compilado
- Após compilação, o RPO é atualizado automaticamente (não precisa reiniciar para fontes)
- Alterações em .ch (includes) exigem recompilar todos os fontes que os usam

---

## Diagnóstico de Performance

### Quando usar
Quando usuários reportam lentidão no sistema.

### Procedimento
1. Verificar métricas do AppServer (CPU, memória, threads)
2. Analisar console.log para queries lentas (> 5s)
3. Verificar locks no banco de dados
4. Checar número de conexões ativas vs limite
5. Verificar se há jobs/schedules concorrentes consumindo recursos
6. Analisar índices das tabelas mais acessadas (SIX vs físico)
7. Se necessário, executar rebuild de índices

### Indicadores
- CPU > 80% sustentado: possível loop infinito ou excesso de threads
- Memória > 90%: possível memory leak, verificar MAXSTRINGSIZE
- Queries > 5s: falta de índice ou lock de tabela
- Threads > 200: excesso de usuários ou conexões não liberadas

---

## Verificação de Integridade do Dicionário

### Procedimento via AtuDIC
1. Acessar módulo Banco de Dados → Integridade
2. Selecionar conexão de origem
3. Executar verificação (20 checks automáticos)
4. Analisar resultados por categoria (campos, índices, tabelas, metadados)
5. Para problemas encontrados, usar Equalizador para corrigir

### Checks Principais
- Campos no SX3 sem coluna física correspondente
- Colunas físicas sem entrada no SX3
- Índices no SIX sem índice físico correspondente
- Tabelas no SX2 sem tabela física
- Tipos divergentes (SX3 vs coluna física)
- TOP_FIELD desatualizado
