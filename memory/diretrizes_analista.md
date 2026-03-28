# Diretrizes do Analista Protheus

> Fonte: Base de regras e boas praticas (extraiRPO)
> Total: 12 diretrizes

---

## MVC

### MVC — Estrutura básica
Fontes MVC do Protheus usam funções padrão: ModelDef(), ViewModel(), ViewDef(). A função ModelDef define os campos e regras. ViewModel conecta model e view. Pontos de Entrada em MVC: antes/depois de cada operação CRUD.

### MVC — Validações no Model
Validações em MVC devem ser feitas no ModelDef via regra de campo. User functions de validação devem seguir padrão U_NOME. Campos obrigatórios no MVC são definidos via oModel:SetRequiredMark().

## PE

### PE — PARAMIXB e retorno
Todo PE recebe parâmetros via PARAMIXB (array). Verificar a documentação do PE para saber o que cada posição contém. O retorno correto depende do PE: alguns retornam NIL, outros precisam retornar .T./.F. ou valor específico.

### PE — Pontos de entrada comuns
MT410BRW: navegação no pedido de venda. A410OK: confirma inclusão/alteração. MT410CAN: cancelamento. A410CPOS: após posicionamento. Para NF: MT100GRV (gravação NF saída), MT103GRV (NF entrada).

## QUERY

### Query — Alias obrigatório
Todo campo em query SQL deve ter alias explícito quando há mais de uma tabela: SELECT SA1.A1_COD, SC5.C5_NUM... Sem alias, o DBAccess pode retornar colunas ambíguas.

### Query — MSQuery e performance
Evite MSQuery com LIKE '%termo%' (full scan). Prefira índices: SetOrder + SEEK ou SQL com índice. Para grandes volumes, use TCQUERY com LIMIT.

### Query — RECNO em subquery
Nunca use R_E_C_N_O_ em subqueries ou JOINs. Use sempre as chaves de negócio (ex: filial+código). RECNO pode mudar após reindexação.

## SX3

### SX3 — Campo virtual vs real
Campo virtual (X3_VIRTUAL=S) não existe fisicamente no banco. Não use virtual para campos obrigatórios nem para campos usados em índices. Campos virtuais têm inicializador obrigatório.

### SX3 — Campos customizados
Campos customizados SEMPRE devem ter Z no sufixo do nome (A1_ZCOD, não A1_COD). Prefixo padrão: primeiras 2 letras do alias da tabela. Tamanho máximo depende do banco (SQL Server: 8000 para C, Oracle: 4000).

### SX3 — Obrigatoriedade e ExecAutos
Ao tornar um campo obrigatório, VERIFICAR todos os ExecAutos que gravam na tabela. Se o ExecAuto não preencher o campo, vai gerar erro em produção. Verificar também integrações WS/API.

## USER_FUNCTION

### User Function — Declaração no fonte
User Function deve ser declarada com 'User Function NOME()' no fonte. A função deve existir em algum fonte no diretório RPO. Se não existir, causa erro 'Function not found' em tempo de execução.

### User Function — Padrão de nomenclatura
User functions customizadas DEVEM começar com U_ (U_VALCOD, U_CALCVAL). Sem U_, o Protheus não reconhece como user function externa. Ao referenciar em campo SX3, use sempre com U_.
