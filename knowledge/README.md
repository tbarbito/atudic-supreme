# Knowledge System — Analista Protheus

Este diretorio contem **todo o conhecimento organizado** do agente Analista Protheus.
Abra `capabilities.yaml` para ver o indice completo de tudo que o agente sabe fazer.

## Estrutura

```
knowledge/
├── capabilities.yaml          # INDICE CENTRAL — comece aqui
├── README.md                  # Este arquivo
│
├── tools/                     # Documentacao de cada tool
│   ├── analise_impacto.yaml   #   O que faz, quando usar, inputs/outputs
│   ├── quem_grava.yaml
│   └── ...
│
├── recipes/                   # Receitas de investigacao
│   ├── campo_obrigatorio.yaml #   Trigger + passos + notas
│   ├── aumento_campo.yaml
│   └── ...
│
├── maps/                      # Dados de referencia Protheus
│   ├── rotinas.yaml           #   Rotinas padrao com prefixos/tabelas
│   ├── conceitos.yaml         #   Conceitos de negocio → rotinas
│   ├── operacoes.yaml         #   Tipos de operacao com keywords
│   └── ...
│
├── prompts/                   # Templates de LLM documentados
│   ├── system_duvida.yaml     #   Prompt por modo
│   ├── verification.yaml      #   Pipeline anti-alucinacao
│   └── ...
│
├── heuristics/                # Regras de decisao do agente
│   ├── uso_tabela.yaml        #   Volumetria → ativo/residual
│   ├── decomposicao.yaml      #   Quando decompor processo
│   └── ...
│
└── tests/                     # Cenarios de validacao
    ├── _shared/               #   Testes universais
    │   └── tests.yaml
    ├── marfrig/               #   Testes especificos do cliente
    │   └── tests.yaml
    └── cliente_b/
        └── tests.yaml
```

## Como usar

### Entender o agente
1. Abra `capabilities.yaml` — lista tudo que existe
2. Clique no arquivo de qualquer item para ver detalhes
3. As receitas mostram como o agente investiga cada tipo de caso

### Adicionar novo conhecimento
1. **Nova tool** → crie doc em `tools/` + registre em `capabilities.yaml`
2. **Nova receita** → crie em `recipes/` + registre em `capabilities.yaml`
3. **Novo mapa** → crie em `maps/` + registre em `capabilities.yaml`
4. **Novo teste** → adicione em `tests/_shared/tests.yaml` ou no cliente especifico

### Rodar testes
```bash
pytest tests/test_knowledge.py
```
Os testes validam que:
- Uma pergunta detecta o action_type correto
- O plano de investigacao inclui as tools esperadas
- Custo: ZERO LLM — tudo local

### Contribuir
- Qualquer pessoa que saiba YAML pode editar
- Git tracked — review por PR, historico, rollback
- Ao resolver um caso novo, considere: "isso deveria virar uma receita?"

## Filosofia
- **Tools** = logica Python com queries SQL (ficam no codigo)
- **Receitas** = como combinar tools (ficam aqui, editaveis sem codigo)
- **Mapas** = dados de referencia (ficam aqui, editaveis sem codigo)
- **Testes** = cenarios reais por cliente (validam que nada quebrou)
