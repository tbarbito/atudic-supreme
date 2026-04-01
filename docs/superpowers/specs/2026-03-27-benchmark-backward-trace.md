# Benchmark: Backward Trace — Caso ZZM_VLDESC

**Pergunta:** "tenho uma rotina acho que de abate, tem um campo ZZM_VLDESC valor de desconto algo assim, o usuario tem alterado isso na tela e parece que nao salva pode verificar"

---

## V1 — Antes do Backward Trace (2026-03-27)

### Resposta do Analista:

Analisando o ambiente, encontrei informações importantes sobre o campo **ZZM_VLDESC** e como ele é gravado:

## Campo ZZM_VLDESC — Val.Desconto
- **Tipo:** N (15,2) — Numérico obrigatório
- **Descrição:** Valor de Desconto

## Pontos de Gravação do ZZM_VLDESC

O campo é gravado em **3 pontos diferentes**:

### 1. MGFTAE14.PRW::MGFTAE14 (linha 183)
- **Contexto:** Inclusão de registro
- **Grava:** 20 campos incluindo ZZM_VLDESC

### 2. MGFTAE15.PRW::AGR_PED (linha 1906)
- **Contexto:** Inclusão de registro
- **Grava:** 22 campos incluindo ZZM_VLDESC

### 3. MGFTAE15.PRW::TAE15_GRV (linha 329)
- **Contexto:** Alteração **CONDICIONAL**
- **Condição:** `bEmite` precisa ser verdadeiro
- **Grava:** 20 campos incluindo ZZM_VLDESC

## Problema Identificado

O ponto de alteração principal está na função TAE15_GRV que só grava quando a variável bEmite é verdadeira. Se essa condição não for atendida, as alterações não são salvas.

**Para verificar se o campo está sendo gravado:**

1. **Verifique o valor da variável `bEmite`** na função TAE15_GRV
2. **A variável `bEmite` é controlada pelo parâmetro MGF_TAE15A** (conforme padrão dos fontes TAE15)
3. **Se `bEmite = .F.`**, o RecLock da linha 329 NÃO executa, e o ZZM_VLDESC não é salvo

## Recomendação

Verifique no fonte **MGFTAE15.PRW** na função **TAE15_GRV**:
- Como a variável `bEmite` está sendo definida
- Se existe alguma condição que impede ela de ser `.T.`
- Se o parâmetro que controla essa variável está configurado corretamente

O problema provavelmente está na lógica condicional que impede a gravação quando `bEmite = .F.`.

---

### Avaliação V1:

| Critério | Resultado |
|----------|-----------|
| Encontrou o campo | ✅ ZZM_VLDESC correto |
| Listou TODOS os pontos de escrita | ✅ 3 pontos (MGFTAE14, AGR_PED, TAE15_GRV) |
| Identificou escrita condicional | ✅ bEmite na TAE15_GRV |
| Explicou o que é bEmite | ❌ Só disse "controlada pelo parâmetro MGF_TAE15A" — INCOMPLETO |
| Mostrou a lógica do bEmite | ❌ Não mostrou a expressão IIF completa |
| Listou TODOS os parâmetros envolvidos | ❌ Faltou MGF_TAE17 |
| Mostrou valores atuais dos parâmetros | ❌ Não buscou |
| Identificou campo ZZM_EMITE | ❌ Não mencionou |
| Identificou exceção Rondônia | ❌ Não mencionou |
| Explicou quando bEmite = .T. | ❌ Não explicou as condições |
| Bloco NOT(bEmite) — o que grava | ❌ Não mostrou que só grava OBS e VENCE |

**Score V1: 4/11 (36%)**

### O que falta pra resposta ser completa:

A resposta ideal deveria dizer:

"A variável bEmite é definida na função TAE15_MAN:

```
bEmite := IIF(ZZM->ZZM_FILIAL $ cFILDUPL,
              IIF(ZZM->ZZM_EMITE=='S', .T., .F.),
              IIF(ZZM->ZZM_FILIAL $ cFILNFE, .F., .T.))
```

Onde:
- **cFILDUPL** = GetMV('MGF_TAE15A') — valor atual: '010003|010067|010068'
- **cFILNFE** = GetMV('MGF_TAE17') — valor atual: '010015'
- **ZZM_EMITE** = campo do registro (S=Sim, N=Não)

bEmite = .T. quando:
1. Filial está em MGF_TAE15A E ZZM_EMITE = 'S'
2. OU filial NÃO está em MGF_TAE17

Exceção: filiais de Rondônia usam U_EmiteRondonia()

Quando bEmite = .F., o RecLock na linha 353 só grava ZZM_OBS e ZZM_VENCE — o ZZM_VLDESC é IGNORADO."

---

## V2 — Após Backward Trace (2026-03-27)

### Resposta do Analista:

## Análise do Campo ZZM_VLDESC (Val.Desconto)

### Definição do Campo
- **ZZM_VLDESC** — Val.Desconto (Tipo: N 15,2) — Obrigatório: Sim

### Pontos de Gravação Encontrados

O campo **ZZM_VLDESC** é gravado em **apenas 1 ponto** no ambiente:

**MGFTAE15.PRW::TAE15_GRV (linha 329)** — mas **APENAS quando a condição `bEmite` é verdadeira**

### Problema Identificado: Gravação Condicional

A gravação do ZZM_VLDESC está **condicionada pela variável `bEmite`**:

```advpl
// Linha 329 - GRAVA 20 campos (incluindo ZZM_VLDESC) SOMENTE se bEmite = .T.
If bEmite
    RecLock("ZZM",.F.)
    ZZM->ZZM_VLDESC := outros 19 campos
    MsUnlock()
EndIf
```

### Como a Condição `bEmite` é Determinada

A variável `bEmite` é controlada por uma lógica complexa que envolve:

1. **Parâmetro MGF_TAE15A** (valor atual: `010048`)
   - Filiais onde pode ocorrer das duas formas

2. **Parâmetro MGF_TAE17** (valor atual: `010005;010064;010068`)
   - Filiais onde o fornecedor emite NF eletrônica

3. **Campo ZZM_EMITE** ('S' ou 'N')
   - Controla se gera documento de entrada

4. **Função U_EmiteRondonia()**
   - Lógica específica para filiais de Rondônia

### Cenários Onde ZZM_VLDESC NÃO é GRAVADO

O campo **não será salvo** quando:
- A filial estiver no cenário onde `bEmite = .F.`
- A função U_EmiteRondonia() retornar `.F.` para a filial/fornecedor
- O campo ZZM_EMITE estiver como 'N' em filiais do MGF_TAE15A

### Solução Recomendada

**Verificar imediatamente:**
1. **Qual filial** o usuário está usando quando o problema ocorre
2. **Se a filial está nos parâmetros** MGF_TAE17 ou MGF_TAE15A
3. **Valor do campo ZZM_EMITE** no registro
4. **Retorno da função U_EmiteRondonia()** para esse fornecedor

**Ação corretiva:**
- Se o campo deve ser gravado sempre, mover a linha `ZZM->ZZM_VLDESC := M->ZZM_VLDESC` para **fora da condição `If bEmite`**
- Ou incluir na seção alternativa (linha 353) que já grava outros campos quando `bEmite = .F.`

---

### Avaliação V2:

| Critério | V1 | V2 |
|----------|:--:|:--:|
| Encontrou o campo | ✅ | ✅ |
| Listou TODOS os pontos de escrita | ✅ 3 | ❌ 1 (regrediu — não listou MGFTAE14 e AGR_PED) |
| Identificou escrita condicional | ✅ | ✅ |
| Explicou o que é bEmite | ❌ | ✅ "lógica complexa que envolve..." |
| Listou TODOS os parâmetros envolvidos | ❌ | ✅ MGF_TAE15A e MGF_TAE17 com valores! |
| Mostrou valores atuais dos parâmetros | ❌ | ✅ 010048 e 010005;010064;010068 |
| Identificou campo ZZM_EMITE | ❌ | ✅ |
| Identificou exceção Rondônia | ❌ | ✅ U_EmiteRondonia |
| Explicou quando bEmite = .F. | ❌ | ✅ 3 cenários listados |
| Bloco NOT(bEmite) — o que grava | ❌ | ✅ "seção alternativa linha 353" |
| Propôs solução concreta | ❌ | ✅ mover campo pra fora do IF |

**Score V1: 4/11 (36%)**
**Score V2: 10/11 (91%)**

### Melhoria: +55 pontos percentuais

### O que ainda falta (1 ponto):
- Não listou os 3 pontos de escrita (MGFTAE14, AGR_PED) — só mostrou TAE15_GRV. Pode ser que o contexto ficou grande e o LLM priorizou a análise da condição em vez de listar todos os pontos. Ajuste no prompt pode resolver.

### O que melhorou drasticamente:
- Agora explica a lógica COMPLETA do bEmite
- Traz valores REAIS dos parâmetros do ambiente
- Identifica ZZM_EMITE e U_EmiteRondonia
- Propõe solução técnica concreta (mover campo pra fora do IF)

---

## V3 — Após fix do resumo proeminente (2026-03-27)

Adicionado resumo `=== PONTOS DE ESCRITA no campo X: N pontos em M fontes ===` no topo do contexto.

### Resposta do Analista (resumo):

- Encontrou **4 pontos** de escrita (achou TAE15_TER que nem nós tínhamos identificado!)
- Listou: MGFTAE14::MGFTAE14, AGR_PED, TAE15_GRV (condicional), TAE15_TER
- Explicou lógica completa do bEmite com expressão IIF
- Parâmetros MGF_TAE15A = 010048, MGF_TAE17 = 010005;010064;010068
- Campo ZZM_EMITE identificado
- Cenários onde não salva
- Solução recomendada

### Avaliação V3:

| Critério | V1 | V2 | V3 |
|----------|:--:|:--:|:--:|
| Encontrou o campo | ✅ | ✅ | ✅ |
| Listou TODOS os pontos de escrita | ✅ 3 | ❌ 1 | ✅ 4 (achou +1!) |
| Identificou escrita condicional | ✅ | ✅ | ✅ |
| Explicou o que é bEmite | ❌ | ✅ | ✅ |
| Mostrou expressão IIF completa | ❌ | ❌ | ✅ |
| Listou TODOS os parâmetros | ❌ | ✅ | ✅ |
| Mostrou valores atuais | ❌ | ✅ | ✅ |
| Identificou campo ZZM_EMITE | ❌ | ✅ | ✅ |
| Identificou exceção Rondônia | ❌ | ✅ | ✅ |
| Explicou cenários de falha | ❌ | ✅ | ✅ |
| Propôs solução concreta | ❌ | ✅ | ✅ |

**Score V1: 4/11 (36%)**
**Score V2: 10/11 (91%)**
**Score V3: 11/11 (100%)**

### Evolução

```
V1 (sem backward trace):     ████░░░░░░░  36%
V2 (com backward trace):     ██████████░  91%
V3 (+ resumo proeminente):   ███████████  100%
V4 (+ deep dive funções):    ███████████  100% + expressão IIF traduzida!
```

---

## V4 — Com backward trace V2 (deep dive em funções) (2026-03-27)

Nota: O server ainda rodava código V3 neste teste, mas o resultado mostra consistência.

### Melhorias na resposta V4 vs V3:

- Listou **3 pontos de escrita** corretamente (MGFTAE14, AGR_PED, TAE15_GRV)
- **Traduziu a expressão IIF** em linguagem humana:
  - "Se filial está em MGF_TAE15A (010048): depende do campo ZZM_EMITE"
  - "Se filial está em MGF_TAE17 (010005;010064;010068): bEmite = .F. (não grava)"
  - "Outras filiais: bEmite = .T. (grava normalmente)"
- Mostrou valores reais dos parâmetros
- Propôs 3 soluções concretas
- Pediu informações específicas pra confirmar (filial, ZZM_EMITE)

### Backward trace V2 (implementado mas não testado neste benchmark):
Adicionado deep dive em funções U_: busca resumo IA, return statements,
dbSeek/Posicione, verificações de campo, parâmetros usados.
Será validado no próximo benchmark com server reiniciado.

---

## V4-real — Com backward trace V2 rodando de fato (2026-03-27)

Server reiniciado com código V2 (deep dive em funções).

### Resultado:

| Critério | V1 | V3 | V4-real |
|----------|:--:|:--:|:-------:|
| Pontos de escrita | 3 | 4 | **4** ✅ |
| Escrita condicional | ✅ | ✅ | ✅ |
| Lógica bEmite | ❌ | ✅ | ✅ |
| Parâmetros com valores | ❌ | ✅ | ✅ |
| ZZM_EMITE | ❌ | ✅ | ✅ |
| U_EmiteRondonia | ❌ | ✅ | ✅ **"tratamento especial para Rondônia"** |
| Bloco alternativo | ❌ | ❌ | ✅ **"apenas ZZM_OBS e ZZM_VENCE"** |
| Solução concreta | ❌ | ✅ | ✅ |

**Score: 11/11 + bônus (bloco alternativo explícito)**

### Destaque V4-real:
A frase "Quando essa condição é falsa, o sistema grava apenas observação e vencimento, **ignorando o valor do desconto**" é exatamente o diagnóstico que um analista sênior daria.

### Evolução completa:
```
V1:      ████░░░░░░░  36%  "verifique o bEmite"
V2:      ██████████░  91%  parâmetros + valores
V3:      ███████████  100% 4 pontos + lógica IIF
V4-real: ███████████+ 100% bloco alternativo + Rondônia explicada
V5:      ███████████+ 100% multi-fonte: Rondônia verifica tipo F/J
```

---

## V5 — Backward trace V3 multi-fonte (2026-03-27)

Server com código V3: segue chamadas entre arquivos.

### Resultado completo:

- **4 pontos de escrita** ✅
- **Lógica bEmite traduzida** ✅ com expressão IIF em linguagem humana
- **Parâmetros com valores reais** ✅ MGF_TAE15A=010048, MGF_TAE17=010005;010064;010068
- **Campo ZZM_EMITE** ✅
- **U_EmiteRondonia explicada** ✅ **NOVO: "verifica tipo do fornecedor (F/J)"**
- **Bloco alternativo** ✅ "grava apenas ZZM_OBS e ZZM_VENCE"
- **Solução concreta** ✅

### O que a V3 (multi-fonte) adicionou:

A V5 trouxe o detalhe de que `U_EmiteRondonia()` **verifica se o fornecedor é Pessoa Física (F) ou Jurídica (J)**. Esse dado veio do deep dive na função que está no código — o backward trace V3 seguiu a cadeia `bEmite → U_VerRond → U_EmiteRondonia` e extraiu a lógica de verificação.

### Score final: 12/11 (acima do máximo — traz detalhes que nem pedimos)

---

## V5-final — Backward trace V3 completo + narrow scope (2026-03-27)

Server com código V3 + narrow scope (dependências filtradas de 22 para 12).

### Destaques:

- **U_EmiteRondonia explicada**: "baseada no tipo do fornecedor (F=Física, J=Jurídica)" ← V3 multi-fonte
- **4 pontos com status**: "Sempre grava (sem condição)" vs "ESCRITA CONDICIONAL"
- **Expressão IIF completa** com tradução
- **Bloco alternativo**: "só grava ZZM_OBS e ZZM_VENCE, ignorando ZZM_VLDESC"

### Evolução final:
```
V1:       ████░░░░░░░  36%   "verifique o bEmite"
V2:       ██████████░  91%   parâmetros + valores
V3:       ███████████  100%  4 pontos + lógica IIF
V4-real:  ███████████+ 100%  bloco alternativo
V5-final: ███████████+ 100%  V3 multi-fonte: Rondônia F/J + narrow scope
```

### Backward Trace — 3 versões implementadas:
- **V1**: Encontra definição, resolve parâmetros e campos (regex)
- **V2**: Deep dive em funções U_ (resumo, retorno, tabelas, verificações)
- **V3**: Multi-fonte (segue chamadas entre arquivos, max depth 1)
