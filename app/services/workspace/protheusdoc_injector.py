"""ProtheusDoc Injector — generates and injects documentation blocks into ADVPL/TLPP sources.

Uses existing function resumos from DB + LLM for functions without resumo.
Preserves original file encoding (cp1252 round-trip safe).
"""
import re
import json
import shutil
import unicodedata
from pathlib import Path
from datetime import datetime


def _sanitize_for_cp1252(text: str) -> str:
    """Ensure text is safe for cp1252 encoding.

    The resumos in the DB are stored as UTF-8 JSON. Some characters
    (smart quotes, em-dash, etc.) exist in UTF-8 but not in cp1252.
    This function replaces problematic chars and ensures round-trip safety.
    """
    if not text:
        return ""
    # Try encoding as cp1252 — if it works, text is safe
    try:
        text.encode("cp1252")
        return text
    except UnicodeEncodeError:
        pass
    # Replace char by char, keeping what cp1252 supports
    result = []
    for ch in text:
        try:
            ch.encode("cp1252")
            result.append(ch)
        except UnicodeEncodeError:
            # Try to normalize (é → e, ã → a, etc.)
            nfkd = unicodedata.normalize("NFKD", ch)
            ascii_chars = [c for c in nfkd if ord(c) < 128]
            if ascii_chars:
                result.append("".join(ascii_chars))
            else:
                result.append("?")
    return "".join(result)


# ── Encoding conversion ──

def convert_to_cp1252(file_path: Path, backup: bool = True) -> dict:
    """Convert a source file from any encoding to cp1252.

    Portuguese characters (ç, ã, é, etc.) exist in both UTF-8 and cp1252,
    so conversion is safe for Protheus files. Characters not representable
    in cp1252 are replaced with the closest ASCII equivalent.

    Returns: {arquivo, original_encoding, converted, chars_replaced, problems}
    """
    raw = file_path.read_bytes()
    if not raw:
        return {"arquivo": file_path.name, "original_encoding": "empty", "converted": False}

    # Detect current encoding
    original_enc = "cp1252"
    content = None
    for enc in ["utf-8", "cp1252", "latin-1"]:
        try:
            content = raw.decode(enc)
            original_enc = enc
            break
        except UnicodeDecodeError:
            continue

    if content is None:
        import chardet
        detected = chardet.detect(raw[:4096])
        original_enc = detected.get("encoding") or "latin-1"
        content = raw.decode(original_enc, errors="replace")

    # Already cp1252? Check by trying to encode
    if original_enc == "cp1252":
        return {
            "arquivo": file_path.name,
            "original_encoding": "cp1252",
            "converted": False,
            "message": "Arquivo ja esta em cp1252",
        }

    # Try direct conversion (works for all Portuguese chars)
    chars_replaced = 0
    problems = []
    safe_content = []

    for i, ch in enumerate(content):
        try:
            ch.encode("cp1252")
            safe_content.append(ch)
        except UnicodeEncodeError:
            # Try NFKD normalization (smart quotes → regular, etc.)
            nfkd = unicodedata.normalize("NFKD", ch)
            replacement = ""
            for c in nfkd:
                try:
                    c.encode("cp1252")
                    replacement += c
                except UnicodeEncodeError:
                    if ord(c) < 128:
                        replacement += c
            if replacement:
                safe_content.append(replacement)
            else:
                safe_content.append("?")
            chars_replaced += 1
            # Track first 10 problems for report
            if len(problems) < 10:
                line_num = content[:i].count('\n') + 1
                problems.append({
                    "line": line_num,
                    "char": repr(ch),
                    "code": f"U+{ord(ch):04X}",
                })

    converted_text = "".join(safe_content)

    # Verify round-trip
    cp1252_bytes = converted_text.encode("cp1252")
    verify = cp1252_bytes.decode("cp1252")
    if verify != converted_text:
        return {
            "arquivo": file_path.name,
            "original_encoding": original_enc,
            "converted": False,
            "message": "Falha na verificacao round-trip",
        }

    # Backup and save
    if backup:
        bak_path = file_path.with_suffix(file_path.suffix + ".utf8.bak")
        shutil.copy2(file_path, bak_path)

    file_path.write_bytes(cp1252_bytes)

    return {
        "arquivo": file_path.name,
        "original_encoding": original_enc,
        "new_encoding": "cp1252",
        "converted": True,
        "size_before": len(raw),
        "size_after": len(cp1252_bytes),
        "chars_replaced": chars_replaced,
        "problems": problems,
    }


# ── Encoding repair ──

# Portuguese word patterns: (before_replacement, after_replacement) -> correct char
# Built from analysis of 99 corrupted Protheus source files.
_PT_REPAIR_PATTERNS = [
    # ção patterns
    (r'a(?:liza|loca|rma|ltera|pura|ifica|niza|ifica|aliza)', r'[?](?:ão|ões)', 'ç'),
    # Common words with ç
    (r'Fun', r'ão', 'ç'),
    (r'grava', r'ão', 'ç'),
    (r'integra', r'ão', 'ç'),
    (r'altera', r'ão', 'ç'),
    (r'Solicita', r'ão', 'ç'),
    (r'apresenta', r'ão', 'ç'),
    (r'posi', r'ão', 'ç'),
    (r'Cria', r'ão', 'ç'),
    (r'Inicializa', r'ão', 'ç'),
    (r'opera', r'ão', 'ç'),
    (r'informa', r'ão', 'ç'),
    (r'configura', r'ão', 'ç'),
    (r'valida', r'ão', 'ç'),
    (r'aprova', r'ão', 'ç'),
    (r'descri', r'ão', 'ç'),
    (r'exce', r'ão', 'ç'),
    (r'a', r'ão', 'ç'),  # generic _ação fallback
    # ç in middle of words
    (r'Cabe', r'alho', 'ç'),
    (r'pre', r'o\b', 'ç'),
    (r'servi', r'o', 'ç'),
    (r'cota', r'ão', 'ç'),
    (r'fun', r'ão', 'ç'),
    (r'lan', r'amento', 'ç'),
    (r'for', r'a\b', 'ç'),  # força
    (r'cabe', r'alho', 'ç'),
    (r'ger', r'ncia', 'ê'),
    # ã patterns
    (r'Gest', r'o\b', 'ã'),
    (r'gest', r'o\b', 'ã'),
    (r'n', r'o\b', 'ã'),  # não
    (r'gr', r'o\b', 'ã'),  # grão
    (r'p', r'o\b', 'ã'),   # pão
    (r'padr', r'o\b', 'ã'),
    # á patterns
    (r'usu', r'rio', 'á'),
    (r'obrigat', r'rio', 'ó'),
    (r'Tempor', r'ri[oa]', 'á'),
    (r'tempor', r'ri[oa]', 'á'),
    (r'rel', r't[oó]rio', 'a'),
    (r'necess', r'rio', 'á'),
    (r'prim', r'rio', 'á'),
    (r'secund', r'rio', 'á'),
    (r'v', r'lid[oa]', 'á'),
    (r'c', r'lculo', 'á'),
    # é patterns
    (r't', r'tulo', 'í'),
    (r'c', r'digo', 'ó'),
    (r'n', r'mero', 'ú'),
    (r'per', r'odo', 'í'),
    # ó patterns
    (r'hist', r'ric', 'ó'),
    (r'obrigat', r'ri', 'ó'),
    (r'relat', r'ri', 'ó'),
]


def repair_corrupted_encoding(file_path: Path, backup: bool = True) -> dict:
    """Repair files where UTF-8 replacement character (U+FFFD = EF BF BD) replaced
    original accented characters.

    Uses Portuguese word patterns to infer the correct character.
    Falls back to common accent heuristics when pattern not found.

    Returns: {arquivo, repaired, chars_fixed, chars_unknown}
    """
    raw = file_path.read_bytes()
    REPL_BYTES = b'\xef\xbf\xbd'

    if REPL_BYTES not in raw:
        return {"arquivo": file_path.name, "repaired": False, "message": "Nenhuma corrupcao encontrada"}

    total_repl = raw.count(REPL_BYTES)

    # Decode as cp1252 to work with text (the REPL bytes decode to ï¿½ in cp1252)
    text = raw.decode('cp1252', errors='replace')
    REPL_STR = '\xef\xbf\xbd'  # How EF BF BD looks in cp1252: ï¿½

    # Strategy 1: Pattern-based repair using Portuguese word knowledge
    chars_fixed = 0
    chars_unknown = 0

    # Common contextual replacements: before + REPL + after -> before + char + after
    # Build from analysis of Portuguese programming comments
    CONTEXT_MAP = {
        # word_before + ? + word_after -> replacement char
        # ção family
        'acao': 'ação', 'ucao': 'ução', 'icao': 'ição',
    }

    # ── Strategy: line-by-line repair ──
    # 1. Lines that are mostly REPL chars → box-drawing borders → replace with ASCII art
    # 2. Individual REPL chars within text → infer Portuguese accents

    lines_raw = raw.split(b'\n')
    result_lines = []

    for line_raw in lines_raw:
        repl_count = line_raw.count(REPL_BYTES)
        if repl_count == 0:
            result_lines.append(line_raw)
            continue

        line_len = len(line_raw)
        repl_byte_len = repl_count * 3
        non_repl_text = line_raw.replace(REPL_BYTES, b'').strip()

        # ── Box-drawing detection ──
        # If >60% of the line bytes are REPL, it's a decorative border line
        is_border = (repl_byte_len > line_len * 0.5 and repl_count >= 5)
        # Also: lines like "//?????...?????" or "//+-----+-----+"
        is_comment_border = (non_repl_text in (b'', b'//', b'/*', b'*/', b'//*', b'*', b'/**')
                             or (non_repl_text.startswith(b'//') and
                                 len(non_repl_text.replace(b'//', b'').strip()) == 0))

        if is_border or is_comment_border:
            # Replace entire line: REPL chars become '-' for borders
            new_line = bytearray()
            k = 0
            while k < len(line_raw):
                if line_raw[k:k+3] == REPL_BYTES:
                    new_line.append(ord('-'))
                    chars_fixed += 1
                    k += 3
                else:
                    new_line.append(line_raw[k])
                    k += 1
            result_lines.append(bytes(new_line))
            continue

        # ── Mixed line: has text + some REPL chars ──
        # Check if it's a table/box row with separators (e.g. "//? Funcao ? Autor ?")
        # Pattern: line starts with // and has multiple REPL acting as separators
        line_text = line_raw.decode('cp1252', errors='replace')
        is_table_row = (repl_count >= 3 and
                        (line_raw.lstrip().startswith(b'//') or line_raw.lstrip().startswith(b'*')) and
                        repl_byte_len > line_len * 0.15)

        new_line = bytearray()
        k = 0
        while k < len(line_raw):
            if line_raw[k:k+3] == REPL_BYTES:
                # Count consecutive REPLs at this position
                count = 0
                j = k
                while j < len(line_raw) and line_raw[j:j+3] == REPL_BYTES:
                    count += 1
                    j += 3

                if is_table_row and count == 1:
                    # Single REPL in a table row → vertical separator '|'
                    new_line.append(ord('|'))
                    chars_fixed += 1
                    k = j
                elif is_table_row and count >= 2:
                    # Multiple consecutive REPLs in table → horizontal border
                    for _ in range(count):
                        new_line.append(ord('-'))
                        chars_fixed += 1
                    k = j
                else:
                    # Regular text with accent corruption
                    before = line_raw[max(0,k-20):k].decode('cp1252', errors='replace')
                    after = line_raw[j:min(len(line_raw),j+20)].decode('cp1252', errors='replace')

                    for pos in range(count):
                        inferred = _infer_accent(before, after, pos, count)
                        if inferred:
                            new_line.extend(inferred.encode('cp1252'))
                            chars_fixed += 1
                            before += inferred
                        else:
                            new_line.append(ord('?'))
                            chars_unknown += 1
                            before += '?'
                    k = j
            else:
                new_line.append(line_raw[k])
                k += 1
        result_lines.append(bytes(new_line))

    result_bytes = b'\n'.join(result_lines)

    if chars_fixed == 0 and chars_unknown == total_repl:
        return {"arquivo": file_path.name, "repaired": False,
                "message": f"{total_repl} corrupcoes encontradas mas nao foi possivel inferir"}

    # Verify it's valid cp1252
    try:
        verify = bytes(result_bytes).decode('cp1252')
    except:
        return {"arquivo": file_path.name, "repaired": False, "message": "Falha na verificacao"}

    # Backup and save
    if backup:
        bak_path = file_path.with_suffix(file_path.suffix + '.corrupted.bak')
        if not bak_path.exists():
            import shutil
            shutil.copy2(file_path, bak_path)

    file_path.write_bytes(bytes(result_bytes))

    return {
        "arquivo": file_path.name,
        "repaired": True,
        "total_corruptions": total_repl,
        "chars_fixed": chars_fixed,
        "chars_unknown": chars_unknown,
    }


def _infer_accent(before: str, after: str, pos: int, total: int) -> str | None:
    """Infer what accented character was lost based on surrounding text.

    Uses Portuguese language patterns common in ADVPL source comments.
    The key insight: when multiple REPLs are consecutive (e.g. integra[?][?]o),
    pos=0 is the first unknown, pos=1 is the second. 'after' is always the text
    AFTER all the REPLs, and 'before' gets updated as we infer each char.
    """
    before_lower = before.lower().rstrip()
    after_lower = after.lower().lstrip()

    # ── MULTI-CHAR SEQUENCES (most common: ção = ç+ã) ──
    # When we have 2 consecutive REPLs + "o", it's almost always "ção"
    if total == 2 and after_lower.startswith('o'):
        if pos == 0:
            return 'ç'  # first char of ção
        if pos == 1:
            return 'ã'  # second char of ção

    # 2 consecutive + "oes" or "es" = ções (çõ+es)
    if total == 2 and (after_lower.startswith('oes') or after_lower.startswith('es')):
        if pos == 0:
            return 'ç'
        if pos == 1:
            return 'õ'

    # ── SINGLE CHAR PATTERNS ──

    # ── ção / ções patterns ──
    if after_lower.startswith('ão') or after_lower.startswith('ões'):
        if before_lower.endswith(('a', 'i', 'u', 'e', 'ra', 'ta', 'la', 'na', 'da', 'sa', 'za', 'ca', 'ga', 'pa', 'ma', 'va', 'ba', 'ja', 'fa', 'xa', 'qua')):
            return 'ç'

    # ...çREPL + o  (ã was lost in "ção")
    if after_lower.startswith('o') and before_lower.endswith('ç'):
        return 'ã'

    # ── é patterns ──
    # Isolated "é" between spaces ("produto é de", "campo é obrigatório")
    if before.endswith((' ', '\t', '"', '(')) and after.startswith((' ', '\t')):
        return 'é'
    if (len(before) >= 2 and before[-1] == ' '
            and len(after) >= 1 and after[0] == ' '):
        return 'é'
    # Word-final é: até, café, você, jacaré, purê
    if total == 1 and before_lower.endswith(('at', 'caf', 'voc', 'jacar', 'pur')):
        after_first = after[0] if after else ''
        if not after_first.isalpha():
            return 'é'

    # ── ã patterns ──
    if after_lower.startswith('o') and not after_lower.startswith('ou') and not after_lower.startswith('os'):
        if before_lower.endswith(('gest', 'est', 'irm', 'org', 'crist', 'padr', 'gr', 'ch',
                                  'serm', 'vers', 'raz', 'sess', 'miss',
                                  'clus', 'lus', 'fun', 'ques', 'cidad',
                                  'situa', 'obriga', 'informa', 'opera', 'configura',
                                  'altera', 'atualiza', 'valida', 'identifica', 'classifica',
                                  'reclama', 'devolu', 'solu', 'execu', 'instru', 'constru',
                                  'distribu', 'diminu', 'evolu', 'substitu', 'contribu',
                                  'redu', 'produ', 'introdu', 'institui', 'recondu',
                                  'posi', 'rela', 'gera', 'migra', 'integra', 'importa',
                                  'exporta', 'nota', 'documenta', 'aprova', 'libera',
                                  'movimenta', 'implementa', 'programa', 'compensa',
                                  'liquida', 'cancela', 'emiss', 'dimens')):
            return 'ã'
        if before_lower.endswith('n') and total == 1:
            return 'ã'  # não

    if after_lower.startswith('es') or after_lower.startswith('os'):
        if before_lower.endswith(('alem', 'org', 'irm', 'cidad', 'condi',
                                  'opera', 'informa', 'configura', 'atualiza',
                                  'altera', 'situa', 'obriga', 'reclama',
                                  'movimenta', 'transa')):
            return 'ã'

    # ── ç patterns (not before ão) ──
    if after_lower.startswith('alho') or after_lower.startswith('alh'):
        return 'ç'  # cabeçalho
    if after_lower.startswith('a') and before_lower.endswith(('for', 'lan', 'dan', 'ren', 'tran', 'crian', 'balan', 'amen', 'lian', 'licen')):
        return 'ç'
    if after_lower.startswith('o') and before_lower.endswith(('pre', 'servi', 'ter', 'comer', 'mar', 'almo', 'ber', 'esfor', 'endere',
                                                               'peda', 'comer', 'reba', 'desconto')):
        return 'ç'
    if after_lower.startswith('os') and before_lower.endswith(('pre', 'servi', 'endere', 'peda')):
        return 'ç'
    if after_lower.startswith('ar') and before_lower.endswith(('al', 'can', 'dan', 'lan', 'com')):
        return 'ç'
    if after_lower.startswith('u') and before_lower.endswith(('a', 'cal')):
        return 'ç'  # açúcar, calçulo

    # ── á patterns ──
    if after_lower.startswith('rio') or after_lower.startswith('ria'):
        if before_lower.endswith(('usu', 'tempor', 'necess', 'prim', 'secund', 'ordin', 'tribut',
                                  'monet', 'unit', 'complement', 'inventar', 'volunt', 'arbitr',
                                  'solid', 'orçament',
                                  'coment', 'hor', 'calend', 'sum', 'contr', 'sal',
                                  'formul', 'bin', 'dicion', 'oper', 'banc', 'fiscal',
                                  'monet', 'tribut', 'finant')):
            return 'á'
        if before_lower.endswith(('obrigat', 'relat', 'alemat')):
            return 'ó'
    if after_lower.startswith('vel') or after_lower.startswith('veis'):
        if before_lower.endswith(('vari', 'aplic', 'aceit', 'compar', 'not', 'cont', 'amig',
                                  'toler', 'vulner', 'impag', 'dur', 'negoci')):
            return 'á'
        if before_lower.endswith(('poss', 'vis', 'dispon', 'compat', 'flex', 'leg', 'acess')):
            return 'í'
    if after_lower.startswith('lid') or after_lower.startswith('lido') or after_lower.startswith('lida'):
        if before_lower.endswith(('v', 'inv')):
            return 'á'
    if after_lower.startswith('lculo') or after_lower.startswith('lcul'):
        return 'á'  # cálculo
    if after_lower.startswith('gina'):
        return 'á'  # página
    if after_lower.startswith('sic'):
        return 'á'  # básico
    if after_lower.startswith('rea') or after_lower.startswith('reas'):
        return 'á'  # área
    if after_lower.startswith('gua'):
        return 'á'  # água
    if after_lower.startswith('bil') and before_lower.endswith(('cont', 'h')):
        return 'á'  # contábil, hábil
    if after_lower.startswith('lise') or after_lower.startswith('lis'):
        if before_lower.endswith(('an',)):
            return 'á'  # análise
    if after_lower.startswith('tico') or after_lower.startswith('tica'):
        if before_lower.endswith(('autom', 'sistem', 'pr', 'tem', 'gram', 'inform')):
            return 'á'
    # Word-final á: já, lá, atrás
    if total == 1 and before_lower.endswith(('j', 'l', 'atr', 'ser')):
        after_first = after[0] if after else ''
        if not after_first.isalpha() or after_lower.startswith('s') and before_lower.endswith('atr'):
            return 'á'

    # ── í patterns ──
    if after_lower.startswith('tulo'):
        return 'í'  # título
    if after_lower.startswith('odo'):
        return 'í'  # período
    if after_lower.startswith('ndice') or after_lower.startswith('ndic'):
        return 'í'  # índice
    if after_lower.startswith('cio') or after_lower.startswith('cios'):
        if before_lower.endswith(('in', 'exerc', 'benef', 'of')):
            return 'í'
    if after_lower.startswith('nimo'):
        return 'í'  # mínimo
    if after_lower.startswith('vel') or after_lower.startswith('veis'):
        if before_lower.endswith(('poss', 'vis', 'dispon', 'compat', 'flex', 'leg', 'acess')):
            return 'í'
    if after_lower.startswith('ncia') or after_lower.startswith('nci'):
        if before_lower.endswith(('prov', 'efic')):
            return 'í'  # província, eficiência→ actually ê, handle below

    # ── ó patterns ──
    if after_lower.startswith('digo'):
        return 'ó'  # código
    if after_lower.startswith('dul'):
        return 'ó'  # módulo
    if after_lower.startswith('gic'):
        return 'ó'  # lógico
    if after_lower.startswith('pia') or after_lower.startswith('pias'):
        return 'ó'  # cópia
    if after_lower.startswith('rmula'):
        return 'ó'  # fórmula
    if after_lower.startswith('rios') and before_lower.endswith(('relat',)):
        return 'ó'  # relatórios

    # ── ú patterns ──
    if after_lower.startswith('mero'):
        return 'ú'  # número
    if after_lower.startswith('nico'):
        if not before_lower.endswith(('eletr',)):  # eletrônico → ô
            return 'ú'  # único
    if after_lower.startswith('ltim'):
        return 'ú'  # último, últimas
    if after_lower.startswith('blico') or after_lower.startswith('blic'):
        return 'ú'  # público
    if after_lower.startswith('til'):
        return 'ú'  # útil
    # Word-start ú: " ?ltim" → "últim"
    if not before_lower or not before_lower[-1].isalpha():
        if after_lower.startswith('ltim'):
            return 'ú'

    # ── ê patterns ──
    if after_lower.startswith('ncia') or after_lower.startswith('nci'):
        if before_lower.endswith(('ger', 'refer', 'pend', 'seq', 'frequ', 'ocorr', 'emerg',
                                  'ag', 'exist', 'apar', 'efici', 'compet', 'perman')):
            return 'ê'
    if after_lower.startswith('s') and before_lower.endswith(('m', 'tr', 'fr')):
        return 'ê'  # mês, três

    # ── ô patterns ──
    if (after_lower.startswith('nico') or after_lower.startswith('nica')) and before_lower.endswith(('eletr',)):
        return 'ô'  # eletrônico, eletrônica

    # ── á patterns (names and remaining words) ──
    if after_lower.startswith('udio') and before_lower.endswith(('cl',)):
        return 'á'  # Cláudio
    if after_lower.startswith('rcio') and before_lower.endswith(('com', 'come')):
        return 'é'  # comércio
    if after_lower.startswith('dio') and before_lower.endswith(('rem', 'inc', 'interme')):
        return 'é'  # remédio, incêndio→ê, intermediário→á
    if after_lower.startswith('cil') and before_lower.endswith(('f', 'dif')):
        return 'á'  # fácil, difícil→í
    if after_lower.startswith('cil') and before_lower.endswith(('dif',)):
        return 'í'  # difícil

    return None


# ── Question mark accent repair ──

# Full-word replacements for multi-char corruption patterns (e.g., UTF-8 ã → ?o)
_WORD_REPLACEMENTS = {
    'inclus?oo': 'inclusão', 'exclus?oo': 'exclusão',
}

def repair_question_marks(content: str) -> tuple[str, dict]:
    """Repair '?' characters that replaced Portuguese accents in source files.

    Strategy (hybrid, 3 layers):
    1. Full-word dictionary for known multi-char corruption (e.g. Inclus?oo → Inclusão)
    2. _infer_accent patterns for single-? inside words (reuses existing Portuguese patterns)
    3. Context rules for word-start and word-end positions

    Only replaces '?' when confidently identified as a corrupted accent.
    Legitimate question marks (end of sentence, standalone) are preserved.

    Returns: (repaired_content, stats_dict)
    """
    stats = {"total_repairs": 0, "words_fixed": []}

    if '?' not in content:
        return content, stats

    # Layer 1: full-word replacements (case-insensitive)
    for pattern, replacement in _WORD_REPLACEMENTS.items():
        if pattern in content.lower():
            import re as _re
            content = _re.sub(_re.escape(pattern), replacement, content, flags=_re.IGNORECASE)
            stats["total_repairs"] += content.lower().count(replacement) - content.lower().count(pattern)

    if '?' not in content:
        return content, stats

    # Layer 2+3: character-level inference
    lines = content.split('\n')
    result_lines = []

    for line in lines:
        if '?' not in line:
            result_lines.append(line)
            continue
        result_lines.append(_repair_line_qmarks(line, stats))

    return '\n'.join(result_lines), stats


def _is_likely_accent(before: str, after: str, count: int) -> bool:
    """Determine if '?' at this position is likely a corrupted accent, not a real '?'."""
    before_ch = before[-1] if before else ''
    after_ch = after[0] if after else ''

    # Inside a word: letter?letter  (e.g., "at?s", "Inclus?o")
    if before_ch.isalpha() and after_ch.isalpha():
        return True

    # Start of word: (space/start)?letter  (e.g., " ?ltimas" → "últimas")
    if (not before_ch or not before_ch.isalpha()) and after_ch.isalpha() and count == 1:
        # Verify _infer_accent can resolve it (avoid false positives)
        inferred = _infer_accent(before, after, 0, 1)
        return inferred is not None

    # End of word: letter?(space/end)  (e.g., "at? " → "até")
    if before_ch.isalpha() and (not after_ch or not after_ch.isalpha()) and count == 1:
        inferred = _infer_accent(before, after, 0, 1)
        return inferred is not None

    return False


def _repair_line_qmarks(line: str, stats: dict) -> str:
    """Repair '?' marks in a single line using _infer_accent."""
    result = []
    i = 0

    while i < len(line):
        if line[i] != '?':
            result.append(line[i])
            i += 1
            continue

        # Count consecutive ?s
        j = i
        while j < len(line) and line[j] == '?':
            j += 1
        count = j - i

        before = ''.join(result)
        after = line[j:]

        if _is_likely_accent(before, after, count):
            temp_before = before
            for pos in range(count):
                inferred = _infer_accent(temp_before, after, pos, count)
                if inferred:
                    result.append(inferred)
                    temp_before += inferred
                    stats["total_repairs"] += 1
                    stats["words_fixed"].append(
                        f"{before[-8:]!r}->'{inferred}'->{after[:8]!r}"
                    )
                else:
                    result.append('?')
        else:
            result.extend(['?'] * count)

        i = j

    return ''.join(result)


# ── Encoding helpers ──

def read_source(file_path: Path) -> tuple[str, str]:
    """Read source file, return (content, detected_encoding)."""
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
    """Write source preserving original encoding without silently corrupting chars."""
    try:
        encoded = content.encode(encoding, errors="strict")
    except UnicodeEncodeError:
        # Sanitize only the chars that can't be encoded, preserve everything else
        sanitized = _sanitize_for_cp1252(content) if encoding == "cp1252" else content
        encoded = sanitized.encode(encoding, errors="replace")
    file_path.write_bytes(encoded)


# ── Function detection ──

_FUNC_RE = re.compile(
    r'^((?:Static\s+|User\s+|Main\s+)?Function\s+(\w+)\s*\(([^)]*)\))'
    r'|^(WSMETHOD\s+(\w+)\s+WS(?:RECEIVE|SEND|SERVICE))'
    r'|^(METHOD\s+(\w+)\s*\(([^)]*)\)\s*CLASS\s+(\w+))',
    re.IGNORECASE | re.MULTILINE,
)

_PROTHEUSDOC_RE = re.compile(
    r'/\*\s*/?\s*\{Protheus\.doc\}\s*(\w+)',
    re.IGNORECASE,
)


def find_functions(content: str) -> list[dict]:
    """Find all function declarations with their line positions."""
    functions = []
    lines = content.split('\n')

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Standard functions
        m = re.match(r'(Static\s+|User\s+|Main\s+)?Function\s+(\w+)\s*\(([^)]*)\)', stripped, re.IGNORECASE)
        if m:
            func_type = (m.group(1) or "").strip() + " Function"
            functions.append({
                "nome": m.group(2),
                "tipo": func_type.strip(),
                "params_raw": m.group(3).strip(),
                "line": i,
                "decl_type": "function",
            })
            continue

        # WSMETHOD
        m = re.match(r'WSMETHOD\s+(\w+)\s+WS(?:RECEIVE|SEND|SERVICE)', stripped, re.IGNORECASE)
        if m:
            functions.append({
                "nome": m.group(1),
                "tipo": "Method",
                "params_raw": "",
                "line": i,
                "decl_type": "wsmethod",
            })
            continue

        # METHOD ... CLASS
        m = re.match(r'METHOD\s+(\w+)\s*\(([^)]*)\)\s*CLASS\s+(\w+)', stripped, re.IGNORECASE)
        if m:
            functions.append({
                "nome": m.group(1),
                "tipo": "Method",
                "params_raw": m.group(2).strip(),
                "line": i,
                "decl_type": "method",
                "class_name": m.group(3),
            })

    return functions


def has_protheusdoc(content: str, func_name: str, func_line: int) -> bool:
    """Check if a function already has a ProtheusDoc block above it."""
    lines = content.split('\n')
    start = max(0, func_line - 30)
    block = '\n'.join(lines[start:func_line])
    pattern = re.compile(r'\{Protheus\.doc\}\s*' + re.escape(func_name), re.IGNORECASE)
    return bool(pattern.search(block))


# ── Old comment parser ──

def _extract_old_comment(content: str, func_line: int) -> dict | None:
    """Find and parse any comment block above a function declaration.

    Handles multiple formats:
    - Block: /* ... */  (descriptive header)
    - ProtheusDoc: /*/{Protheus.doc} ... /*/
    - Single-line: // comments

    Returns dict with extracted fields and line range, or None.
    """
    lines = content.split('\n')
    if func_line <= 0:
        return None

    # Scan upward from the function to find comment block end
    search_start = func_line - 1

    # Skip blank lines above function
    while search_start >= 0 and lines[search_start].strip() == '':
        search_start -= 1

    if search_start < 0:
        return None

    comment_end = -1
    comment_start = -1
    is_block = False

    line = lines[search_start].strip()

    # Check for block comment ending (*/ or /*/)
    if line in ('*/', '/*/'):
        comment_end = search_start
        is_block = True
        # Find the opening /* or /*/{Protheus.doc}
        for j in range(search_start - 1, max(search_start - 50, -1), -1):
            l = lines[j].strip()
            if l.startswith('/*'):
                comment_start = j
                break
    # Check for single-line // comments
    elif line.startswith('//'):
        comment_end = search_start
        comment_start = search_start
        for j in range(search_start - 1, max(search_start - 20, -1), -1):
            if lines[j].strip().startswith('//') or lines[j].strip() == '':
                if lines[j].strip().startswith('//'):
                    comment_start = j
            else:
                break

    if comment_start < 0 or comment_end < 0:
        return None

    comment_text = '\n'.join(lines[comment_start:comment_end + 1])

    # Parse fields from the comment
    extracted = {
        "start_line": comment_start,
        "end_line": comment_end,
        "raw": comment_text,
        "autor": "",
        "data": "",
        "descricao": "",
        "programa": "",
        "doc_origem": "",
        "solicitante": "",
        "obs": "",
        "history": "",
        "is_protheusdoc": '{Protheus.doc}' in comment_text.lower() or '{protheus.doc}' in comment_text,
    }

    for cline in comment_text.split('\n'):
        cl = cline.strip().lstrip('/*').lstrip('/').lstrip('*').strip()
        cl_lower = cl.lower()

        # Author
        if cl_lower.startswith('autor') or cl_lower.startswith('@author') or cl_lower.startswith('author'):
            val = re.sub(r'^(?:autor|@author|author)[.\s:]*', '', cl, flags=re.IGNORECASE).strip()
            if val and val.lower() not in ('', 'nome', 'name'):
                extracted["autor"] = val

        # Date
        elif cl_lower.startswith('data') or cl_lower.startswith('@since') or cl_lower.startswith('date'):
            val = re.sub(r'^(?:data|@since|date)[.\s:]*', '', cl, flags=re.IGNORECASE).strip()
            if val:
                extracted["data"] = val

        # Program name
        elif cl_lower.startswith('programa') or cl_lower.startswith('program'):
            val = re.sub(r'^(?:programa|program)[.\s:]*', '', cl, flags=re.IGNORECASE).strip()
            if val:
                extracted["programa"] = val

        # Description
        elif cl_lower.startswith('descri') or cl_lower.startswith('@description'):
            val = re.sub(r'^(?:descri[a-z\u00e7\u00e3o/]*\s*(?:/\s*objetivo)?|@description)[.\s:]*', '', cl, flags=re.IGNORECASE).strip()
            if val:
                extracted["descricao"] = val

        # Doc origin
        elif cl_lower.startswith('doc') and 'origem' in cl_lower:
            val = re.sub(r'^doc[.\s]*origem[.\s:]*', '', cl, flags=re.IGNORECASE).strip()
            if val:
                extracted["doc_origem"] = val

        # Solicitante
        elif cl_lower.startswith('solicitante'):
            val = re.sub(r'^solicitante[.\s:]*', '', cl, flags=re.IGNORECASE).strip()
            if val:
                extracted["solicitante"] = val

        # Obs
        elif cl_lower.startswith('obs') or cl_lower.startswith('@obs'):
            val = re.sub(r'^(?:obs|@obs)[.\s:]*', '', cl, flags=re.IGNORECASE).strip()
            if val:
                extracted["obs"] = val

        # History
        elif cl_lower.startswith('history') or cl_lower.startswith('@history') or cl_lower.startswith('altera'):
            val = re.sub(r'^(?:history|@history|altera[a-z\u00e7\u00e3o]*)[.\s:]*', '', cl, flags=re.IGNORECASE).strip()
            if val:
                extracted["history"] = val

    # If it's a ProtheusDoc, also try to get the description from the first content line
    if extracted["is_protheusdoc"] and not extracted["descricao"]:
        plines = comment_text.split('\n')
        for pl in plines[1:]:  # Skip the /*/{Protheus.doc} line
            pl = pl.strip()
            if pl and not pl.startswith('@') and not pl.startswith('/*') and not pl.startswith('/*/'):
                extracted["descricao"] = pl
                break

    return extracted


def _validate_old_comment(extracted: dict, file_name: str, func_name: str) -> dict:
    """Validate if old comment is trustworthy.

    Checks:
    1. Program name matches the actual file/function
    2. Description seems related to the actual code

    Returns extracted dict with added 'descricao_confiavel' flag.
    """
    extracted["descricao_confiavel"] = True
    stem = file_name.replace('.prw', '').replace('.PRW', '').replace('.prx', '').replace('.tlpp', '')

    # Check if program name matches
    prog = extracted.get("programa", "").strip().upper()
    if prog:
        if prog != stem.upper() and prog != func_name.upper():
            # Program name doesn't match file — likely copied from another fonte
            extracted["descricao_confiavel"] = False

    return extracted


def _merge_descriptions(old_desc: str, ia_desc: str, confiavel: bool) -> str:
    """Merge old and AI descriptions.

    - If old is NOT trustworthy: use only IA
    - If old IS trustworthy: combine both (old context + IA analysis)
    """
    if not ia_desc:
        return old_desc or ""
    if not old_desc:
        return ia_desc
    if not confiavel:
        return ia_desc

    # Both exist and old is trustworthy — combine
    # Avoid repeating if they say the same thing
    old_lower = old_desc.lower()[:60]
    ia_lower = ia_desc.lower()[:60]

    # If very similar (first 60 chars), use IA (more detailed)
    if old_lower == ia_lower:
        return ia_desc

    # Combine: IA description + original context
    return f"{ia_desc} (Original: {old_desc})"


# ── ProtheusDoc block generation ──

def build_protheusdoc_block(
    func_name: str,
    description: str,
    func_type: str = "Function",
    author: str = "ExtraiRPO",
    params: list[dict] | None = None,
    return_info: str = "",
    tables: list[str] | None = None,
    obs: str = "",
    since: str = "",
    history: str = "",
) -> str:
    """Build a ProtheusDoc comment block. All text is sanitized for cp1252."""
    # Sanitize all text fields for cp1252 safety
    description = _sanitize_for_cp1252(description)
    author = _sanitize_for_cp1252(author)
    return_info = _sanitize_for_cp1252(return_info)
    obs = _sanitize_for_cp1252(obs)
    history = _sanitize_for_cp1252(history)

    lines = []
    lines.append(f"/*/{'{'}Protheus.doc{'}'} {func_name}")
    lines.append(description)

    # @type
    if "method" in func_type.lower() or func_type == "Method":
        lines.append("@type Method")
    else:
        lines.append("@type Function")

    # @author
    lines.append(f"@author {author}")

    # @since
    lines.append(f"@since {since or datetime.now().strftime('%d/%m/%Y')}")

    # @param
    if params:
        for p in params:
            p_type = p.get("tipo", "variant")
            p_desc = _sanitize_for_cp1252(p.get("descricao", ""))
            lines.append(f"@param {p['nome']}, {p_type}, {p_desc}")

    # @return
    if return_info:
        lines.append(f"@return {return_info}")

    # @table
    if tables:
        lines.append(f"@table {', '.join(tables)}")

    # @obs
    if obs:
        lines.append(f"@obs {obs}")

    # @history
    if history:
        lines.append(f"@history {history}")

    lines.append("/*/")
    return '\n'.join(lines)


def generate_protheusdoc_from_resumo(
    func_name: str,
    resumo_json: str,
    func_info: dict,
    old_comment: dict | None = None,
    file_name: str = "",
) -> str:
    """Generate ProtheusDoc block merging AI resumo + old comment data.

    Priority:
    - Author/Date: from old comment (original dev), fallback to ExtraiRPO/today
    - Description: merge if old is trustworthy, IA-only if not
    - Tables/Return/Obs: from IA analysis
    - Doc origem/Solicitante: preserved in @obs from old comment
    """
    ia_description = ""
    params = []
    return_info = ""
    tables = []
    obs_parts = []
    author = "ExtraiRPO"
    since = datetime.now().strftime("%d/%m/%Y")
    history = ""

    # Parse resumo JSON (IA analysis)
    try:
        parsed = json.loads(resumo_json)
        ia_description = parsed.get("humano", "")
        ia = parsed.get("ia", {})

        tab_leitura = ia.get("tabelas_leitura", [])
        tab_escrita = ia.get("tabelas_escrita", [])
        tables = sorted(set(tab_leitura + tab_escrita))

        ret_tipo = ia.get("retorno_tipo", "")
        ret_desc = ia.get("retorno_descricao", "")
        if ret_tipo and ret_desc:
            return_info = f"{ret_tipo}, {ret_desc}"
        elif ret_tipo:
            return_info = f"{ret_tipo}, Retorno da funcao"
        elif ret_desc:
            return_info = f"variant, {ret_desc}"

        impacto = ia.get("impacto", "")
        acao = ia.get("acao", "")
        if acao:
            obs_parts.append(f"Acao: {acao}")
        if impacto:
            obs_parts.append(f"Impacto: {impacto}")

    except (json.JSONDecodeError, TypeError):
        ia_description = resumo_json[:200] if resumo_json else ""

    # Merge with old comment if available
    if old_comment:
        # Validate old comment
        validated = _validate_old_comment(old_comment, file_name, func_name)

        # Author — always prefer original author
        if validated.get("autor"):
            author = validated["autor"]

        # Date — always prefer original date
        if validated.get("data"):
            since = validated["data"]
            # Add history entry for our documentation
            history = f"{datetime.now().strftime('%d/%m/%Y')}, ExtraiRPO, Documentacao gerada por IA"

        # Description — merge based on trustworthiness
        old_desc = validated.get("descricao", "")
        confiavel = validated.get("descricao_confiavel", True)
        description = _merge_descriptions(old_desc, ia_description, confiavel)

        # Preserve doc_origem and solicitante in @obs
        if validated.get("doc_origem"):
            obs_parts.append(f"Doc Origem: {validated['doc_origem']}")
        if validated.get("solicitante"):
            obs_parts.append(f"Solicitante: {validated['solicitante']}")
        if validated.get("obs") and validated["obs"] not in obs_parts:
            obs_parts.append(validated["obs"])

        # Preserve old history
        if validated.get("history"):
            if history:
                history = f"{validated['history']}. {history}"
            else:
                history = validated["history"]
    else:
        description = ia_description

    if not description:
        description = f"Funcao {func_name}"

    # Parse params from raw signature
    params_raw = func_info.get("params_raw", "")
    if params_raw:
        for p in params_raw.split(","):
            p = p.strip()
            if p:
                params.append({"nome": p, "tipo": "variant", "descricao": ""})

    if not tables and func_info.get("tabelas_ref"):
        tables = func_info["tabelas_ref"]

    obs = ". ".join(obs_parts) if obs_parts else ""

    return build_protheusdoc_block(
        func_name=func_name,
        description=description,
        func_type=func_info.get("tipo", "Function"),
        author=author,
        since=since,
        params=params if params else None,
        return_info=return_info,
        tables=tables if tables else None,
        obs=obs,
        history=history,
    )


# ── Main injection logic ──

def inject_protheusdoc(
    content: str,
    func_name: str,
    doc_block: str,
    func_line: int,
) -> str:
    """Inject a ProtheusDoc block before a function declaration."""
    lines = content.split('\n')

    # Find the right insertion point (before the function, after any blank lines)
    insert_at = func_line

    # Skip blank lines above the function to place the doc right before
    while insert_at > 0 and lines[insert_at - 1].strip() == '':
        insert_at -= 1

    # Add a blank line before and after the doc block
    doc_lines = [''] + doc_block.split('\n') + ['']

    # Remove double blank lines
    if insert_at > 0 and lines[insert_at - 1].strip() == '':
        doc_lines = doc_lines[1:]  # Remove leading blank if already blank above

    lines[insert_at:insert_at] = doc_lines

    return '\n'.join(lines)


def process_fonte(
    file_path: Path,
    func_resumos: dict[str, str],
    func_details: dict[str, dict],
    backup: bool = True,
    dry_run: bool = False,
) -> dict:
    """Process a source file: extract old comments, merge with IA, replace.

    Flow per function:
    1. Find old comment above function (any format)
    2. Extract: autor, data, descricao, doc_origem, etc.
    3. Validate: program name matches? description trustworthy?
    4. Merge: trustworthy old desc + IA desc, or IA-only if not trustworthy
    5. Generate new ProtheusDoc block
    6. Remove old comment
    7. Insert new ProtheusDoc

    Returns:
        {arquivo, encoding, total_functions, injected, replaced, blocks: [...]}
    """
    content, encoding = read_source(file_path)

    # Repair corrupted accents (? replacing Portuguese chars) before processing
    content, qmark_stats = repair_question_marks(content)

    functions = find_functions(content)
    file_name = file_path.name

    result = {
        "arquivo": file_name,
        "encoding": encoding,
        "total_functions": len(functions),
        "qmark_repairs": qmark_stats.get("total_repairs", 0),
        "injected": 0,
        "replaced": 0,
        "kept": 0,
        "blocks": [],
    }

    # Collect all operations: (func, old_comment_range, new_block)
    operations = []
    for func in functions:
        name = func["nome"]
        resumo = func_resumos.get(name, "")
        details = func_details.get(name, func)

        # Extract old comment above this function
        old_comment = _extract_old_comment(content, func["line"])

        # Check if it already has our ProtheusDoc (previously generated by ExtraiRPO)
        if old_comment and old_comment.get("is_protheusdoc"):
            # Check if it's OUR protheusdoc (has ExtraiRPO author)
            if "ExtraiRPO" in old_comment.get("raw", ""):
                result["kept"] += 1
                continue

        # Generate new block with merged data
        doc_block = generate_protheusdoc_from_resumo(
            func_name=name,
            resumo_json=resumo,
            func_info=details,
            old_comment=old_comment,
            file_name=file_name,
        )

        action = "replace" if old_comment else "inject"
        operations.append({
            "func": func,
            "block": doc_block,
            "old_comment": old_comment,
            "action": action,
        })
        result["blocks"].append({
            "funcao": name,
            "line": func["line"],
            "block": doc_block,
            "has_resumo": bool(resumo),
            "action": action,
            "old_autor": old_comment.get("autor", "") if old_comment else "",
            "old_descricao_confiavel": old_comment.get("descricao_confiavel", True) if old_comment else True,
        })

    if dry_run:
        result["injected"] = sum(1 for o in operations if o["action"] == "inject")
        result["replaced"] = sum(1 for o in operations if o["action"] == "replace")
        return result

    if not operations:
        return result

    # Apply operations in REVERSE order (bottom to top) to preserve line numbers
    lines = content.split('\n')

    for op in reversed(operations):
        func = op["func"]
        func_name = func["nome"]

        # Find current function line in the (potentially modified) lines
        func_line = -1
        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.match(r'(?:Static\s+|User\s+|Main\s+)?Function\s+' + re.escape(func_name) + r'\b',
                        stripped, re.IGNORECASE) or \
               re.match(r'WSMETHOD\s+' + re.escape(func_name) + r'\b', stripped, re.IGNORECASE) or \
               re.match(r'METHOD\s+' + re.escape(func_name) + r'\b', stripped, re.IGNORECASE):
                func_line = i
                break

        if func_line < 0:
            continue

        # Step 1: Remove old comment if exists
        if op["old_comment"]:
            old = op["old_comment"]
            # Recalculate old comment position relative to current func_line
            old_start = old["start_line"]
            old_end = old["end_line"]

            # Verify the old comment is still at expected position
            # (check if the content at old_start looks like a comment)
            if old_start >= 0 and old_end < len(lines):
                check_line = lines[old_start].strip()
                if check_line.startswith('/*') or check_line.startswith('//'):
                    # Remove old comment lines (including trailing blank lines)
                    del lines[old_start:old_end + 1]
                    # Adjust func_line since we removed lines above
                    removed_count = old_end - old_start + 1
                    func_line -= removed_count
                    result["replaced"] += 1
                else:
                    result["injected"] += 1
            else:
                result["injected"] += 1
        else:
            result["injected"] += 1

        # Step 2: Insert new ProtheusDoc block before the function
        insert_at = func_line
        # Skip blank lines above to place doc right before function
        while insert_at > 0 and lines[insert_at - 1].strip() == '':
            insert_at -= 1

        doc_lines = [''] + op["block"].split('\n')

        # Avoid double blank line at top
        if insert_at > 0 and lines[insert_at - 1].strip() == '':
            doc_lines = doc_lines[1:]

        lines[insert_at:insert_at] = doc_lines

    # Save
    modified_content = '\n'.join(lines)

    if backup:
        bak_path = file_path.with_suffix(file_path.suffix + '.bak')
        shutil.copy2(file_path, bak_path)
    write_source(file_path, modified_content, encoding)

    return result
