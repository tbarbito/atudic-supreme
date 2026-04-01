"""Analista Orchestrator — demand classifier and entity extractor for the Peça ao Analista pipeline."""

import json
import re

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

CLASSIFY_PROMPT = """Você é um classificador de demandas técnicas de consultores TOTVS Protheus.

## Tipos de demanda

| Tipo        | Quando usar | Exemplos |
|-------------|-------------|---------|
| bug         | Erro em produção, error log, programa que travou ou retorna valor errado | "Está dando FATAL ERROR no MATA410", "programa bugado", "erro no log" |
| campo       | Criar ou alterar campo no dicionário SX3 (validação, obrigatoriedade, tipo, tamanho, inicializador, gatilho, F3) | "criar campo A1_ZCODINT na SA1", "alterar tamanho do campo", "adicionar gatilho" |
| parametro   | Criar ou alterar parâmetro SX6 (MV_XXXX, MGF_XXXX) | "criar parâmetro MV_SLDNEG", "alterar conteúdo do MV_INTTIPO" |
| sx1         | Criar ou alterar grupo de perguntas SX1 (wizard de configuração) | "criar pergunta no grupo AFA001", "alterar SX1 de fechamento" |
| sx5         | Criar ou alterar tabela genérica/combo SX5 | "nova opção na tabela 05 do SX5", "criar tabela genérica para tipos de contrato" |
| projeto     | Nova funcionalidade, ponto de entrada (PE), novo fonte (.prw/.tlpp), relatório, integração, automação | "criar relatório de estoque", "ponto de entrada no faturamento", "integração com ERP externo" |
| job_schedule| Agendamento, schedule, job periódico, rotina automática | "agendar processamento diário", "schedule para gerar boletos", "job noturno" |

## Padrões Protheus que você deve reconhecer

- **Campos**: formato XX_YYYY (ex: A1_COD, C5_NUM, C6_PRODUTO, B1_DESC)
- **Parâmetros**: MV_XXXX ou MGF_XXXX (ex: MV_SLDNEG, MV_INTTIPO, MGF_VLIMIT)
- **Tabelas**: SA1, SA2, SB1, SB2, SC5, SC6, SD1, SD2, SE1, SE2, SF1, SF2, SF3, SFT, SIX, SX3, SX5, SX6, SX7, SX9, etc.
- **Fontes**: arquivos .prw, .PRW, .tlpp, .TLPP
- **Grupos SX1**: 3 letras + 3 dígitos (ex: AFA001, COM010)
- **Módulos**: sigla de 3 letras (FAT, COM, EST, FIN, PCP, CTB, RH, CMP)

## Instruções

1. Classifique a demanda em UM dos 7 tipos acima.
2. Extraia APENAS entidades mencionadas explicitamente ou claramente implícitas. NÃO invente.
3. Gere search_terms: palavras-chave relevantes para busca semântica (sem stopwords).
4. Escreva um resumo técnico de 1 frase.
5. Retorne JSON PURO, sem markdown, sem ```json, sem explicações.

## Formato de saída

{
  "tipo": "campo",
  "confianca": 0.95,
  "entidades": {
    "tabelas": ["SA1"],
    "campos": ["A1_ZCODINT"],
    "fontes": [],
    "parametros": ["MV_INTTIPO"],
    "grupos_sx1": [],
    "tabelas_sx5": [],
    "modulos": []
  },
  "search_terms": ["campo", "validacao", "SA1", "integracao"],
  "resumo": "Criar campo A1_ZCODINT na SA1 com validação baseada no parâmetro MV_INTTIPO"
}"""

# ---------------------------------------------------------------------------
# Common Protheus table aliases for regex detection
# ---------------------------------------------------------------------------

_PROTHEUS_TABLES = [
    "SA0", "SA1", "SA2", "SA3", "SA4", "SA5", "SA6", "SA7", "SA8", "SA9",
    "SAB", "SAC", "SAD",
    "SB1", "SB2", "SB3", "SB4", "SB5", "SB6", "SB7", "SB8", "SB9",
    "SC1", "SC2", "SC3", "SC4", "SC5", "SC6", "SC7", "SC8", "SC9",
    "SD1", "SD2", "SD3", "SD4", "SD5", "SD6", "SD7", "SD8", "SD9",
    "SE1", "SE2", "SE3", "SE4", "SE5", "SE6", "SE7", "SE8", "SE9",
    "SF1", "SF2", "SF3", "SF4", "SF5", "SFA", "SFB", "SFT",
    "SG1", "SG2", "SG3",
    "SH1", "SH2", "SH3",
    "SI1", "SI2",
    "SIX",
    "SK1", "SK2",
    "SL1", "SL2",
    "SM0", "SM1", "SM2",
    "SN1", "SN2",
    "SO1", "SO2",
    "SP1", "SP2",
    "SQ1", "SQ2",
    "SR1", "SR2",
    "SS1", "SS2",
    "ST1", "ST2", "ST3", "ST4", "ST5", "ST6", "ST7", "ST8",
    "SU1", "SU2",
    "SV1", "SV2",
    "SW1", "SW2",
    "SX1", "SX2", "SX3", "SX5", "SX6", "SX7", "SX9",
    "SY1", "SY2",
    "SZ1", "SZ2",
]

# Build a compiled pattern for table detection (word-boundary, case-sensitive)
_TABLE_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in _PROTHEUS_TABLES) + r")\b"
)

# Field pattern: XX_YYYYY (2 alphanum prefix, underscore, word chars)
_FIELD_PATTERN = re.compile(r"\b([A-Z][A-Z0-9]_\w+)\b")

# Parameter pattern
_PARAM_PATTERN = re.compile(r"\b(MV_\w+|MGF_\w+)\b", re.IGNORECASE)

# Source file pattern
_FONTE_PATTERN = re.compile(r"\b(\w+\.(?:prw|PRW|tlpp|TLPP))\b")

# SX1 group pattern: 3 uppercase letters + 3 digits
_SX1_PATTERN = re.compile(r"\b([A-Z]{3}\d{3})\b")

# Module pattern: 3 uppercase letters that are known module abbreviations
_KNOWN_MODULES = {
    "FAT", "COM", "EST", "FIN", "PCP", "CTB", "RH", "CMP", "FIS",
    "UTL", "MNT", "GFE", "AFT", "RHU", "SIG",
}
_MODULE_PATTERN = re.compile(r"\b([A-Z]{3})\b")


# ---------------------------------------------------------------------------
# extract_entities_from_text
# ---------------------------------------------------------------------------

def extract_entities_from_text(text: str) -> dict:
    """Pure-regex entity extraction from a demand text.

    Detects Protheus fields, parameters, source files, SX1 groups, table aliases
    and module abbreviations. Used as fallback and complement to LLM extraction.

    Returns a dict matching the 'entidades' structure.
    """
    # Fields: XX_YYYYY — filter out false positives (must have at least 1 char after underscore)
    campos = list(dict.fromkeys(
        m for m in _FIELD_PATTERN.findall(text)
        if len(m.split("_", 1)[1]) >= 1
    ))

    # Parameters (normalize to uppercase)
    parametros = list(dict.fromkeys(m.upper() for m in _PARAM_PATTERN.findall(text)))

    # Remove parameters from campos to avoid duplicates (e.g. MV_INTTIPO)
    campos = [c for c in campos if c.upper() not in {p.upper() for p in parametros}]

    # Source files
    fontes = list(dict.fromkeys(_FONTE_PATTERN.findall(text)))

    # SX1 groups — exclude known table aliases to avoid overlap (e.g. "SX3" could match)
    sx1_raw = _SX1_PATTERN.findall(text)
    _tables_set = set(_PROTHEUS_TABLES)
    grupos_sx1 = list(dict.fromkeys(g for g in sx1_raw if g not in _tables_set))

    # Tables
    tabelas = list(dict.fromkeys(_TABLE_PATTERN.findall(text)))

    # Tabelas SX5: look for numeric table codes after "tabela" context clues or standalone 2-digit codes
    # Simple heuristic: digits like "05", "AF" after SX5 mention
    tabelas_sx5_pattern = re.compile(r"\bSX5\b.*?\b([A-Z0-9]{2})\b", re.IGNORECASE)
    tabelas_sx5 = list(dict.fromkeys(tabelas_sx5_pattern.findall(text)))

    # Modules: 3 uppercase letters from known set
    modulos = list(dict.fromkeys(
        m for m in _MODULE_PATTERN.findall(text)
        if m in _KNOWN_MODULES
    ))

    return {
        "tabelas": tabelas,
        "campos": campos,
        "fontes": fontes,
        "parametros": parametros,
        "grupos_sx1": grupos_sx1,
        "tabelas_sx5": tabelas_sx5,
        "modulos": modulos,
    }


# ---------------------------------------------------------------------------
# _empty_entidades / _empty_result
# ---------------------------------------------------------------------------

def _empty_entidades() -> dict:
    return {
        "tabelas": [],
        "campos": [],
        "fontes": [],
        "parametros": [],
        "grupos_sx1": [],
        "tabelas_sx5": [],
        "modulos": [],
    }


def _fallback_result(demand_text: str) -> dict:
    return {
        "tipo": "projeto",
        "confianca": 0.3,
        "entidades": _empty_entidades(),
        "search_terms": [],
        "resumo": demand_text[:100],
    }


# ---------------------------------------------------------------------------
# _merge_entidades
# ---------------------------------------------------------------------------

def _merge_entidades(llm_ent: dict, regex_ent: dict) -> dict:
    """Merge LLM-extracted entities with regex-extracted ones (union, no duplicates)."""
    merged = {}
    keys = ["tabelas", "campos", "fontes", "parametros", "grupos_sx1", "tabelas_sx5", "modulos"]
    for key in keys:
        llm_list = llm_ent.get(key) or []
        regex_list = regex_ent.get(key) or []
        # Preserve order: LLM first, then regex extras
        seen = dict.fromkeys(llm_list)
        for item in regex_list:
            if item not in seen:
                seen[item] = None
        merged[key] = list(seen.keys())
    return merged


# ---------------------------------------------------------------------------
# _strip_markdown_json
# ---------------------------------------------------------------------------

def _strip_markdown_json(text: str) -> str:
    """Remove ```json ... ``` fences if present."""
    text = text.strip()
    if text.startswith("```"):
        # Remove first line (``` or ```json) and trailing ```
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]
    return text.strip()


# ---------------------------------------------------------------------------
# classify_demand
# ---------------------------------------------------------------------------

def classify_demand(llm, demand_text: str) -> dict:
    """Classify a consultant demand using the LLM and enrich with regex entity extraction.

    Args:
        llm: An LLMService instance (must have a _call method).
        demand_text: The raw demand text from the consultant.

    Returns:
        A dict with keys: tipo, confianca, entidades, search_terms, resumo.
        Never raises — always returns something usable.
    """
    messages = [
        {"role": "system", "content": CLASSIFY_PROMPT},
        {"role": "user", "content": demand_text},
    ]

    last_error = None
    raw = ""
    for attempt in range(2):
        try:
            raw = llm._call(messages, temperature=0.1, use_gen=True)
            cleaned = _strip_markdown_json(raw)
            result = json.loads(cleaned)

            # Validate required keys
            if "tipo" not in result:
                raise ValueError("Missing 'tipo' in LLM response")

            # Ensure entidades dict is well-formed
            llm_ent = result.get("entidades") or {}
            for key in ["tabelas", "campos", "fontes", "parametros", "grupos_sx1", "tabelas_sx5", "modulos"]:
                if key not in llm_ent or not isinstance(llm_ent[key], list):
                    llm_ent[key] = []

            # Regex complement
            regex_ent = extract_entities_from_text(demand_text)
            result["entidades"] = _merge_entidades(llm_ent, regex_ent)

            # Ensure other fields exist
            result.setdefault("confianca", 0.5)
            result.setdefault("search_terms", [])
            result.setdefault("resumo", demand_text[:100])

            return result

        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            last_error = exc
            # On first failure, add a correction hint and retry
            if attempt == 0:
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": (
                        "Sua resposta não é JSON válido. "
                        "Retorne APENAS o JSON puro, sem markdown, sem texto adicional."
                    ),
                })
        except Exception as exc:
            last_error = exc
            break

    # All attempts failed — return safe fallback enriched with regex
    fallback = _fallback_result(demand_text)
    fallback["entidades"] = extract_entities_from_text(demand_text)
    return fallback
