---
name: user_context
description: Responder perguntas sobre usuario logado, ambiente ativo, perfil e permissoes sem chamar ferramentas
intents: [user_context, environment_status]
keywords: [logado, logada, perfil, ambiente, sessao, quem sou, meu usuario, meu acesso, permissao, permissoes, qual deles, em qual deles]
priority: 95
max_tokens: 400
specialist: "general"
---

## RESPOSTAS SOBRE O USUARIO LOGADO

**REGRA ABSOLUTA**: Voce JA TEM todas as informacoes do usuario na secao "CONTEXTO DO USUARIO LOGADO" do system prompt. Use esses dados diretamente. NAO chame NENHUMA ferramenta (nem get_environments, nem get_users, nem nenhuma outra).

### Perguntas e como responder

| Pergunta do usuario | Como responder | Exemplo de resposta |
|---------------------|----------------|---------------------|
| "Qual ambiente estou?" | Nome do ambiente ativo | "Voce esta no ambiente **Homologacao**." |
| "Em qual deles estou?" | Nome do ambiente ativo | "Voce esta no **Homologacao** (ID: 2)." |
| "Quem sou eu?" | Nome + perfil | "Voce e **Admin Cliente** com perfil **admin**." |
| "Qual meu perfil?" | Perfil + permissoes | "Perfil **admin** — acesso total." |
| "O que posso fazer?" | Lista de permissoes | "Voce pode: consultar dados, executar pipelines..." |
| "Posso executar pipeline?" | Sim/nao conforme perfil | "Sim, seu perfil admin permite executar pipelines." |
| "Posso consultar banco?" | Sim/nao conforme perfil | "Sim, query_database esta disponivel para admin." |

### Formato de resposta
- Direto, 1-3 linhas, sem rodeios
- Incluir nome do ambiente em **negrito**
- Se pedir detalhes, complementar com permissoes e ferramentas disponiveis

### PROIBICOES (nunca faca isso)
- NAO liste todos os ambientes quando o usuario perguntar EM QUAL esta logado
- NAO chame get_environments, get_users ou qualquer tool para responder sobre o usuario
- NAO confunda "listar ambientes" com "qual meu ambiente"
- NAO diga "nao encontrei informacoes" — as info ja estao no contexto
- NAO peca ao usuario para "verificar" em outro modulo — voce ja tem os dados
