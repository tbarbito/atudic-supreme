# Skill: ProtheusDoc — Documentação Inline de Fontes ADVPL/TLPP

## Objetivo

Esta skill define o padrão para gerar blocos de documentação ProtheusDoc em fontes ADVPL/TLPP.
O agente de IA usa estas regras para criar comentários estruturados que são reconhecidos pelo
TDS (TOTVS Developer Studio), VS Code e ferramentas de documentação automática.

---

## 1. Encoding dos Fontes Protheus

### Regra de ouro: NUNCA converter encoding

Os fontes Protheus (.prw, .prx, .tlpp) usam **Windows-1252 (cp1252)** como encoding padrão.
Acentos como ç, ã, é são bytes cp1252 (ex: ç = 0xE7, ã = 0xE3).

### Fluxo seguro para leitura e escrita

```
LEITURA:
  1. Ler arquivo como bytes brutos (read_bytes)
  2. Tentar decodificar como cp1252 (99% dos casos)
  3. Fallback: utf-8 → chardet → latin-1

ESCRITA:
  1. Decodificar bytes originais com o encoding detectado
  2. Manipular como string Python (inserir comentários)
  3. Encodificar DE VOLTA com o MESMO encoding original
  4. Salvar bytes brutos (write_bytes)
```

### Código de referência

```python
def read_source(file_path: Path) -> tuple[str, str]:
    """Lê fonte e retorna (conteúdo, encoding_detectado)."""
    raw = file_path.read_bytes()
    if not raw:
        return "", "cp1252"
    for enc in ["cp1252", "utf-8"]:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    import chardet
    detected = chardet.detect(raw[:4096])
    enc = detected.get("encoding") or "latin-1"
    try:
        return raw.decode(enc), enc
    except (UnicodeDecodeError, LookupError):
        return raw.decode("latin-1"), "latin-1"


def write_source(file_path: Path, content: str, encoding: str):
    """Salva fonte preservando encoding original."""
    file_path.write_bytes(content.encode(encoding, errors="replace"))
```

### Regras de encoding para comentários

- Comentários gerados pela IA devem usar **apenas ASCII** nos tags (@author, @since, etc.)
- O campo de descrição livre pode conter acentos — serão salvos em cp1252 normalmente
- NUNCA usar caracteres Unicode especiais (emojis, setas →, bullets •)
- Usar apenas: letras, números, acentos portugueses (á, é, í, ó, ú, ã, õ, ç), pontuação básica

---

## 2. Formato ProtheusDoc

### Estrutura do bloco

```advpl
/*/{Protheus.doc} NomeDaFuncao
Descricao breve em 1-2 frases do objetivo da funcao.
@type Function
@author Nome do Autor
@since DD/MM/YYYY
@version 1.0
@param cNomeParam, character, Descricao do parametro
@param nValor, numeric, Valor numerico usado no calculo
@return logical, .T. se processou com sucesso
@table SC7, SA2, SF2
@obs Observacao importante sobre uso ou restricao
@see MATA120, U_MGFFAT70
/*/
```

### Regras do bloco

1. Abertura: `/*/{Protheus.doc} NomeDaFuncao` (sem espaco antes do `/*`)
2. Primeira linha apos abertura: descricao breve (1-2 frases)
3. Tags na ordem: @type, @author, @since, @version, @param, @return, @table, @obs, @history, @see
4. Fechamento: `/*/` (em linha propria)
5. O bloco fica ANTES da declaracao da funcao (na linha imediatamente anterior)

### Tags disponíveis

| Tag | Obrigatoria | Formato | Descricao |
|---|---|---|---|
| `@type` | Sim | `@type Function\|Method\|Class` | Tipo do elemento |
| `@author` | Sim | `@author Nome Sobrenome` | Autor original |
| `@since` | Sim | `@since DD/MM/YYYY` | Data de criacao |
| `@version` | Nao | `@version 1.0` | Versao do codigo |
| `@description` | Nao | `@description Texto longo...` | Descricao detalhada (quando a breve nao basta) |
| `@param` | Se tiver params | `@param nome, tipo, descricao` | Um por parametro |
| `@return` | Se tiver retorno | `@return tipo, descricao` | Tipo e descricao do retorno |
| `@table` | Recomendado | `@table SC7, SA2, SF2` | Tabelas acessadas (leitura e escrita) |
| `@obs` | Nao | `@obs Texto livre` | Observacoes, restricoes, avisos |
| `@history` | Nao | `@history DD/MM/YYYY, Autor, Descricao da alteracao` | Historico de alteracoes |
| `@see` | Nao | `@see MATA120, U_OutraFunc` | Referencias a outras funcoes ou rotinas |
| `@sample` | Nao | `@sample U_MinhaFunc("001", .T.)` | Exemplo de chamada |

### Tipos de @param

| Tipo ADVPL | Valor no @param |
|---|---|
| Character | `character` |
| Numeric | `numeric` |
| Logical | `logical` |
| Date | `date` |
| Array | `array` |
| Object | `object` |
| Block | `codeblock` |
| Variant | `variant` |

### Tipos de @return

| Retorno | Formato |
|---|---|
| Logico | `@return logical, .T. se valido, .F. se invalido` |
| Numerico | `@return numeric, Codigo do registro gerado` |
| Texto | `@return character, Nome formatado do cliente` |
| Array | `@return array, Array com {codigo, descricao, valor}` |
| Nil/Nenhum | `@return nil, Sem retorno` |

---

## 3. Regras para o Agente de IA

### O que gerar

Para cada funcao no fonte, gerar um bloco ProtheusDoc com:

1. **Descricao**: Analisar o codigo e descrever o OBJETIVO DE NEGOCIO (nao o tecnico)
   - BOM: "Valida se o pedido de compra atende as regras de alcada do cliente"
   - RUIM: "Percorre array e verifica condicoes com IF/ENDIF"

2. **@param**: Analisar a assinatura e o uso de cada parametro no codigo
   - Se o parametro e recebido mas o tipo nao e claro, usar `variant`
   - Se tem valor default, mencionar na descricao

3. **@return**: Analisar o que a funcao retorna
   - Se nao tem Return explicito ou retorna nil, usar `@return nil, Sem retorno`
   - Se retorna .T./.F., explicar o que cada valor significa

4. **@table**: Listar tabelas que a funcao acessa
   - Usar dados ja extraidos pelo parser (tabelas_ref, write_tables)
   - Formato: tabelas separadas por virgula

5. **@type**: Determinar pelo tipo de declaracao
   - `User Function` → `@type Function`
   - `Static Function` → `@type Function`
   - `Method ... Class` → `@type Method`
   - `WSMETHOD` → `@type Method`

### O que NAO gerar

- NAO gerar bloco para funcoes que JA TEM ProtheusDoc (verificar se existe `{Protheus.doc}` antes)
- NAO remover ou alterar blocos existentes
- NAO adicionar tags vazias (se nao tem @obs, nao incluir `@obs `)
- NAO usar `//TODO Descricao auto-gerada` — sempre gerar descricao real
- NAO gerar descricoes genericas como "Funcao auxiliar" ou "Processamento de dados"

### Posicionamento do bloco

```advpl
// ANTES (sem ProtheusDoc):
Static Function ValidaPedido(cPedido, lForce)
    Local lRet := .T.
    ...

// DEPOIS (com ProtheusDoc):
/*/{Protheus.doc} ValidaPedido
Valida se o pedido de compra atende as regras de negocio antes da gravacao.
Verifica alcada, status do fornecedor e disponibilidade de estoque.
@type Function
@author ExtraiRPO
@since 23/03/2026
@param cPedido, character, Numero do pedido de compra (C7_NUM)
@param lForce, logical, .T. para forcar aprovacao sem alcada
@return logical, .T. se o pedido e valido para gravacao
@table SC7, SA2, SB1
@obs Chamada pelo PE MT120LOK antes do commit
/*/
Static Function ValidaPedido(cPedido, lForce)
    Local lRet := .T.
    ...
```

### Para funcoes sem parametros

```advpl
/*/{Protheus.doc} MenuDef
Define as opcoes do menu da rotina de cadastro.
@type Function
@author ExtraiRPO
@since 23/03/2026
@return array, Array com opcoes do menu {titulo, acao, acesso, operacao}
/*/
Static Function MenuDef()
```

### Para WebService Methods

```advpl
/*/{Protheus.doc} POST
Recebe solicitacao de reenvio de integracao da hierarquia de vendas.
Valida o JSON recebido e processa o reenvio para o cliente/vendedor informado.
@type Method
@author ExtraiRPO
@since 23/03/2026
@return logical, .T. se processou o reenvio com sucesso
@table SA1, SA3
@obs Endpoint REST: POST /mgfwss91/reenvio
/*/
WSMETHOD POST WSSERVICE MGFWSS91
```

---

## 4. Validacao antes de salvar

Antes de injetar o comentario no fonte, o agente DEVE verificar:

1. **Backup**: Criar copia do fonte original antes de modificar (.prw.bak)
2. **Encoding**: Confirmar que o encoding detectado e cp1252 ou utf-8
3. **Sintaxe**: Verificar que o bloco ProtheusDoc esta bem formado (abre e fecha correto)
4. **Posicao**: Verificar que o bloco esta na linha imediatamente antes da declaracao da funcao
5. **Duplicata**: NAO inserir se ja existe `{Protheus.doc}` para essa funcao
6. **Compilacao**: O fonte modificado deve continuar compilavel (comentario nao afeta execucao)

---

## 5. Metadados extras (campos custom ExtraiRPO)

Alem das tags padrao, podemos adicionar tags custom que o ProtheusDoc ignora mas nossa ferramenta parseia:

```advpl
/*/{Protheus.doc} MGFFAT70
Rotina de alteracao de itens do pedido de venda tipo Taura.
@type Function
@author thiago.queiroz
@since 02/10/2019
@table SC5, SC6, SB1
@x-processo faturamento
@x-impacto alto
@x-modulo SIGAFAT
@x-gerado ExtraiRPO 23/03/2026
/*/
```

Tags com prefixo `@x-` sao ignoradas pelo TDS/ProtheusDoc mas parseadas pela nossa ferramenta.
Usar apenas quando necessario — as tags padrao cobrem 90% dos casos.

---

## 6. Referencia rapida — Template por tipo

### User Function (programa principal)
```
/*/{Protheus.doc} NOMEPROG
Descricao do programa e seu objetivo de negocio.
@type Function
@author Nome
@since DD/MM/YYYY
@version 1.0
@param parametros se houver
@return tipo, descricao
@table tabelas principais
@obs observacoes relevantes
/*/
```

### Static Function (funcao interna)
```
/*/{Protheus.doc} NomeFunc
Descricao do que a funcao faz no contexto do programa.
@type Function
@author Nome
@since DD/MM/YYYY
@param parametros
@return tipo, descricao
@table tabelas se acessar diretamente
/*/
```

### WSMETHOD (metodo REST/SOAP)
```
/*/{Protheus.doc} METODO
Descricao do endpoint e o que ele processa.
@type Method
@author Nome
@since DD/MM/YYYY
@return tipo, descricao do response
@table tabelas acessadas
@obs Endpoint: VERBO /caminho/do/endpoint
/*/
```

### METHOD ... CLASS (metodo de classe)
```
/*/{Protheus.doc} NomeMetodo
Descricao do metodo no contexto da classe.
@type Method
@author Nome
@since DD/MM/YYYY
@param parametros
@return tipo, descricao
/*/
```
