import json
import re
from app.services.workspace.workspace_db import Database
from typing import Optional


class KnowledgeService:
    def __init__(self, db: Database):
        self.db = db

    # ── Table deep info with cross-references ──

    def get_table_info(self, tabela: str) -> Optional[dict]:
        row = self.db.execute("SELECT * FROM tabelas WHERE codigo = ?", (tabela,)).fetchone()
        if not row:
            return None

        campos = self.db.execute(
            "SELECT campo, tipo, tamanho, decimal, titulo, descricao, validacao, inicializador, obrigatorio, custom, "
            "f3, cbox, vlduser, when_expr, proprietario, browse, trigger_flag, visual, context, folder "
            "FROM campos WHERE tabela = ?", (tabela,)).fetchall()
        indices = self.db.execute(
            "SELECT ordem, chave, descricao, proprietario, nickname, custom FROM indices WHERE tabela = ?", (tabela,)).fetchall()
        # Gatilhos: match by tabela field OR by field prefix (A1_ for SA1, C5_ for SC5, etc)
        prefix = tabela[1:] + "_"  # SA1 -> A1_, SC5 -> C5_, SE1 -> E1_
        gatilhos = self.db.execute(
            "SELECT campo_origem, campo_destino, regra, tipo, custom, condicao, proprietario, alias FROM gatilhos "
            "WHERE tabela = ? OR campo_origem LIKE ? OR campo_destino LIKE ?",
            (tabela, prefix + "%", prefix + "%")).fetchall()

        # Cross-reference: relationships (SX9)
        rel_origem = self.db.execute(
            "SELECT tabela_destino, expressao_origem, expressao_destino, custom "
            "FROM relacionamentos WHERE tabela_origem = ?", (tabela,)).fetchall()
        rel_destino = self.db.execute(
            "SELECT tabela_origem, expressao_origem, expressao_destino, custom "
            "FROM relacionamentos WHERE tabela_destino = ?", (tabela,)).fetchall()

        # Cross-reference: F3 lookups (SXB) for fields in this table
        consultas_f3 = {}
        for c in campos:
            campo_nome = c[0]
            # Check if any campo has a F3 validation referencing SXB
            validacao = c[6] or ""
            if "ExistCpo" in validacao or "F3" in validacao:
                consultas_f3[campo_nome] = validacao

        # Cross-reference: generic tables (SX5) used in validations
        combos = {}
        for c in campos:
            campo_nome = c[0]
            inicializador = c[7] or ""
            validacao = c[6] or ""
            # Detect SX5 combo references like Pertence("XX") or X3_CBOX
            for ref_str in [inicializador, validacao]:
                if "Pertence(" in ref_str or "X5" in ref_str:
                    combos[campo_nome] = ref_str

        campos_list = []
        for c in campos:
            campo_dict = {
                "campo": c[0], "tipo": c[1], "tamanho": c[2], "decimal": c[3],
                "titulo": c[4], "descricao": c[5], "validacao": c[6],
                "inicializador": c[7], "obrigatorio": bool(c[8]), "custom": bool(c[9]),
                "f3": c[10] or "", "cbox": c[11] or "", "vlduser": c[12] or "",
                "when_expr": c[13] or "", "proprietario": c[14] or "S",
                "browse": c[15] or "", "trigger_flag": c[16] or "",
                "visual": c[17] or "", "context": c[18] or "", "folder": c[19] or "",
            }
            # Enrich with cross-references
            if c[0] in consultas_f3:
                campo_dict["f3_validacao"] = consultas_f3[c[0]]
            if c[0] in combos:
                campo_dict["combo_ref"] = combos[c[0]]
            campos_list.append(campo_dict)

        return {
            "codigo": row[0], "nome": row[1], "modo": row[2], "custom": bool(row[3]),
            "campos": campos_list,
            "campos_custom": [c for c in campos_list if c["custom"]],
            "campos_obrigatorios": [c for c in campos_list if c["obrigatorio"]],
            "indices": [{"ordem": i[0], "chave": i[1], "descricao": i[2], "proprietario": i[3], "nickname": i[4], "custom": bool(i[5])} for i in indices],
            "indices_custom": [{"ordem": i[0], "chave": i[1], "descricao": i[2]} for i in indices if i[5]],
            "gatilhos": [{"campo_origem": g[0], "campo_destino": g[1], "regra": g[2], "tipo": g[3], "custom": bool(g[4]), "condicao": g[5], "proprietario": g[6], "alias": g[7]} for g in gatilhos],
            "gatilhos_custom": [{"campo_origem": g[0], "campo_destino": g[1], "regra": g[2], "condicao": g[5]} for g in gatilhos if g[4]],
            "relacionamentos_saida": [{"tabela_destino": r[0], "expr_origem": r[1], "expr_destino": r[2], "custom": bool(r[3])} for r in rel_origem],
            "relacionamentos_entrada": [{"tabela_origem": r[0], "expr_origem": r[1], "expr_destino": r[2], "custom": bool(r[3])} for r in rel_destino],
        }

    # ── Module-level queries ──

    def get_tables_for_module(self, modulo: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT DISTINCT tabelas_ref FROM fontes WHERE modulo = ?", (modulo,)).fetchall()
        tables = set()
        for row in rows:
            if row[0]:
                tables.update(json.loads(row[0]))
        return [self.get_table_info(t) for t in sorted(tables) if self.get_table_info(t)]

    def get_fontes_for_module(self, modulo: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT arquivo, tipo, funcoes, user_funcs, pontos_entrada, tabelas_ref FROM fontes WHERE modulo = ?",
            (modulo,)).fetchall()
        return [{
            "arquivo": r[0], "tipo": r[1],
            "funcoes": json.loads(r[2]) if r[2] else [],
            "user_funcs": json.loads(r[3]) if r[3] else [],
            "pontos_entrada": json.loads(r[4]) if r[4] else [],
            "tabelas_ref": json.loads(r[5]) if r[5] else [],
        } for r in rows]

    def get_parametros_for_module(self, modulo: str) -> list[dict]:
        """Get MV_ parameters referenced in module sources via validations/initializers."""
        fontes = self.get_fontes_for_module(modulo)
        tabelas = set()
        for f in fontes:
            tabelas.update(f["tabelas_ref"])

        params = set()
        # Search parameters referenced in campo validations and initializers
        for tab in tabelas:
            campos = self.db.execute(
                "SELECT validacao, inicializador FROM campos WHERE tabela = ?", (tab,)).fetchall()
            for c in campos:
                for text in [c[0] or "", c[1] or ""]:
                    # Find MV_ references
                    for match in re.findall(r'MV_\w+', text):
                        params.add(match.strip())

        if not params:
            return []

        result = []
        for p in sorted(params):
            rows = self.db.execute(
                "SELECT variavel, tipo, descricao, conteudo, custom FROM parametros WHERE variavel LIKE ?",
                (f"%{p}%",)).fetchall()
            for r in rows:
                result.append({
                    "variavel": r[0].strip(), "tipo": r[1], "descricao": r[2],
                    "conteudo": r[3], "custom": bool(r[4]),
                })
        return result

    def get_relacionamentos_for_tables(self, tabelas: list[str]) -> list[dict]:
        """Get all SX9 relationships involving the given tables."""
        if not tabelas:
            return []
        placeholders = ",".join(["?"] * len(tabelas))
        rows = self.db.execute(
            f"SELECT tabela_origem, identificador, tabela_destino, expressao_origem, expressao_destino, custom "
            f"FROM relacionamentos WHERE tabela_origem IN ({placeholders}) OR tabela_destino IN ({placeholders})",
            tuple(tabelas) + tuple(tabelas)).fetchall()
        return [{
            "tabela_origem": r[0], "identificador": r[1], "tabela_destino": r[2],
            "expr_origem": r[3], "expr_destino": r[4], "custom": bool(r[5]),
        } for r in rows]

    def get_consultas_f3(self, aliases: list[str]) -> list[dict]:
        """Get SXB consultation definitions for given aliases."""
        if not aliases:
            return []
        placeholders = ",".join(["?"] * len(aliases))
        rows = self.db.execute(
            f"SELECT alias, tipo, sequencia, coluna, descricao, conteudo "
            f"FROM consultas WHERE alias IN ({placeholders})", tuple(aliases)).fetchall()
        return [{
            "alias": r[0], "tipo": r[1], "sequencia": r[2],
            "coluna": r[3], "descricao": r[4], "conteudo": r[5],
        } for r in rows]

    def get_tabelas_genericas(self, tabela_ids: list[str]) -> list[dict]:
        """Get SX5 generic table entries."""
        if not tabela_ids:
            return []
        placeholders = ",".join(["?"] * len(tabela_ids))
        rows = self.db.execute(
            f"SELECT tabela, chave, descricao, custom FROM tabelas_genericas "
            f"WHERE tabela IN ({placeholders})", tuple(tabela_ids)).fetchall()
        return [{
            "tabela": r[0], "chave": r[1], "descricao": r[2], "custom": bool(r[3]),
        } for r in rows]

    # ── Summary ──

    def get_custom_summary(self) -> dict:
        campos_custom = self.db.execute("SELECT COUNT(*) FROM campos WHERE custom = 1").fetchone()[0]
        tabelas_custom = self.db.execute("SELECT COUNT(*) FROM tabelas WHERE custom = 1").fetchone()[0]
        gatilhos_custom = self.db.execute("SELECT COUNT(*) FROM gatilhos WHERE custom = 1").fetchone()[0]
        fontes_custom = self.db.execute("SELECT COUNT(*) FROM fontes WHERE tipo = 'custom'").fetchone()[0]

        # New counts
        params_custom = self._safe_count("SELECT COUNT(*) FROM parametros WHERE custom = 1")
        rel_custom = self._safe_count("SELECT COUNT(*) FROM relacionamentos WHERE custom = 1")
        tab_gen_custom = self._safe_count("SELECT COUNT(*) FROM tabelas_genericas WHERE custom = 1")

        return {
            "campos_custom": campos_custom, "tabelas_custom": tabelas_custom,
            "gatilhos_custom": gatilhos_custom, "fontes_custom": fontes_custom,
            "parametros_custom": params_custom, "relacionamentos_custom": rel_custom,
            "tabelas_genericas_custom": tab_gen_custom,
        }

    def _safe_count(self, sql: str) -> int:
        try:
            return self.db.execute(sql).fetchone()[0]
        except Exception:
            return 0

    # ── Vinculos queries ──

    def get_vinculos_for_module(self, modulo: str) -> list[dict]:
        """Get all vinculos for a given module."""
        rows = self.db.execute(
            "SELECT tipo, origem_tipo, origem, destino_tipo, destino, modulo, contexto, peso "
            "FROM vinculos WHERE modulo = ? ORDER BY tipo, peso DESC",
            (modulo.upper(),)).fetchall()
        return [{
            "tipo": r[0], "origem_tipo": r[1], "origem": r[2],
            "destino_tipo": r[3], "destino": r[4], "modulo": r[5],
            "contexto": r[6], "peso": r[7],
        } for r in rows]

    def _get_vinculos_by_tipo(self, vinculos: list[dict], tipo: str) -> list[dict]:
        return [v for v in vinculos if v["tipo"] == tipo]

    def _get_rotinas_from_vinculos(self, vinculos: list[dict]) -> dict:
        """Extract rotina -> {pes, fontes, funcoes} mapping from vinculos."""
        rotinas = {}
        for v in vinculos:
            if v["tipo"] == "pe_afeta_rotina":
                rot = v["destino"]
                rotinas.setdefault(rot, {"pes": [], "fontes": set(), "funcoes": set()})
                rotinas[rot]["pes"].append({"pe": v["origem"], "fonte": v["contexto"]})
                if v["contexto"]:
                    rotinas[rot]["fontes"].add(v["contexto"])
            elif v["tipo"] == "fonte_chama_funcao":
                # Associate fonte with rotinas via PEs
                pass
        return rotinas

    # ── Deep context builder for LLM ──

    def build_context_for_module(self, modulo: str) -> str:
        """Build structured markdown context for LLM agents.

        Output follows the 19-section Base Cliente template structure.
        Organized by rotina when possible. Includes vinculos, indices,
        F3 references, valid_customizada, and all new SX3/SIX/SX7 fields.
        Target: under 30,000 characters.
        """
        mod = modulo.upper()
        lines = [f"# Contexto do Módulo {mod}\n"]

        # ── Gather all data ──
        tables = self.get_tables_for_module(modulo)
        all_table_codes = [t["codigo"] for t in tables] if tables else []
        fontes = self.get_fontes_for_module(modulo)
        params = self.get_parametros_for_module(modulo)
        vinculos = self.get_vinculos_for_module(modulo)
        rels = self.get_relacionamentos_for_tables(all_table_codes)

        # Classify fontes
        custom_fontes = [f for f in fontes if f["tipo"] == "custom"]
        standard_fontes = [f for f in fontes if f["tipo"] != "custom"]

        # Vinculos by tipo
        v_pe_rotina = self._get_vinculos_by_tipo(vinculos, "pe_afeta_rotina")
        v_campo_funcao = self._get_vinculos_by_tipo(vinculos, "campo_valida_funcao")
        v_gatilho_funcao = self._get_vinculos_by_tipo(vinculos, "gatilho_executa_funcao")
        v_fonte_tabela_r = self._get_vinculos_by_tipo(vinculos, "fonte_le_tabela")
        v_fonte_tabela_w = self._get_vinculos_by_tipo(vinculos, "fonte_escreve_tabela")
        v_fonte_funcao = self._get_vinculos_by_tipo(vinculos, "fonte_chama_funcao")
        v_campo_f3 = self._get_vinculos_by_tipo(vinculos, "campo_consulta_tabela")
        v_integracoes = self._get_vinculos_by_tipo(vinculos, "modulo_integra_modulo")

        # Build rotina map from vinculos
        rotina_map = {}  # rotina -> {pes, fontes_custom, tabelas}
        for v in v_pe_rotina:
            rot = v["destino"]
            rotina_map.setdefault(rot, {"pes": [], "fontes": set()})
            rotina_map[rot]["pes"].append({"pe": v["origem"], "fonte": v["contexto"]})
            if v["contexto"]:
                rotina_map[rot]["fontes"].add(v["contexto"])

        # ── Section 1: Resumo Quantitativo ──
        total_campos = sum(len(t["campos"]) for t in tables) if tables else 0
        total_custom = sum(len(t["campos_custom"]) for t in tables) if tables else 0
        total_indices = sum(len(t["indices"]) for t in tables) if tables else 0
        total_indices_custom = sum(len(t["indices_custom"]) for t in tables) if tables else 0
        total_gatilhos = sum(len(t["gatilhos"]) for t in tables) if tables else 0
        total_gatilhos_custom = sum(len(t["gatilhos_custom"]) for t in tables) if tables else 0
        tabelas_custom_list = [t for t in tables if t["custom"]] if tables else []

        lines.append("## 1. Resumo Quantitativo\n")
        lines.append(f"| Item | Padrão | Custom | Total |")
        lines.append(f"|------|--------|--------|-------|")
        lines.append(f"| Campos | {total_campos - total_custom} | {total_custom} | {total_campos} |")
        lines.append(f"| Índices | {total_indices - total_indices_custom} | {total_indices_custom} | {total_indices} |")
        lines.append(f"| Gatilhos | {total_gatilhos - total_gatilhos_custom} | {total_gatilhos_custom} | {total_gatilhos} |")
        lines.append(f"| Fontes custom | — | {len(custom_fontes)} | {len(custom_fontes)} |")
        lines.append(f"| PEs identificados | — | {len(v_pe_rotina)} | {len(v_pe_rotina)} |")
        lines.append(f"| Parâmetros MV_ | — | {len(params)} | {len(params)} |")
        lines.append(f"| Vínculos | — | {len(vinculos)} | {len(vinculos)} |")

        if tabelas_custom_list:
            custom_names = ", ".join("`" + t["codigo"] + "`" for t in tabelas_custom_list)
            lines.append(f"\n**Tabelas Custom:** {custom_names}")

        # ── Section 2: Parametrização ──
        if params:
            lines.append("\n## 2. Parâmetros MV_\n")
            lines.append("| Parâmetro | Tipo | Descrição | Valor | Custom |")
            lines.append("|-----------|------|-----------|-------|--------|")
            for p in params[:40]:  # Limit to avoid bloat
                tag = "Sim" if p["custom"] else "Não"
                val = (p["conteudo"] or "").strip()[:40]
                lines.append(f"| `{p['variavel']}` | {p['tipo']} | {(p['descricao'] or '')[:50]} | `{val}` | {tag} |")

        # ── Section 3: Cadastros — Campos Customizados por Tabela ──
        if tables:
            lines.append("\n## 3. Campos Customizados por Tabela\n")
            for t in tables:
                if not t["campos_custom"] and not t["indices_custom"] and not t["gatilhos_custom"]:
                    continue
                lines.append(f"### {t['codigo']} — {t['nome']} {'[CUSTOM]' if t['custom'] else ''}")

                if t["campos_custom"]:
                    lines.append("\n| Campo | Título | Tipo | Tam | Obrig | F3 | CBOX | VLDUSER | Valid | Inicializador |")
                    lines.append("|-------|--------|------|-----|-------|----|------|---------|-------|---------------|")
                    for c in t["campos_custom"]:
                        obr = "Sim" if c.get("obrigatorio") else ""
                        f3 = c.get("f3", "")
                        cbox = (c.get("cbox") or "")[:30]
                        vld = (c.get("vlduser") or "")[:40]
                        valid = (c.get("validacao") or "")[:40]
                        ini = (c.get("inicializador") or "")[:40]
                        lines.append(f"| `{c['campo']}` | {c['titulo']} | {c['tipo']} | {c['tamanho']},{c['decimal']} | {obr} | {f3} | {cbox} | `{vld}` | `{valid}` | `{ini}` |")

                # Fields with user validation (valid_customizada) — standard fields that have VLDUSER
                vlduser_fields = [c for c in t["campos"] if not c["custom"] and c.get("vlduser")]
                if vlduser_fields:
                    lines.append(f"\n**Campos padrão com VLDUSER (validação customizada):**")
                    for c in vlduser_fields[:15]:
                        lines.append(f"- `{c['campo']}` ({c['titulo']}): `{c['vlduser']}`")

                # F3 references (campos that link to other tables)
                f3_fields = [c for c in t["campos"] if c.get("f3")]
                if f3_fields:
                    lines.append(f"\n**Referências F3 (consultas):**")
                    for c in f3_fields[:20]:
                        lines.append(f"- `{c['campo']}` → F3=`{c['f3']}`")

                # CBOX fields (combo values)
                cbox_fields = [c for c in t["campos_custom"] if c.get("cbox")]
                if cbox_fields:
                    lines.append(f"\n**CBox (combos) customizados:**")
                    for c in cbox_fields:
                        lines.append(f"- `{c['campo']}` ({c['titulo']}): `{c['cbox']}`")

                # Custom indices
                if t["indices_custom"]:
                    lines.append(f"\n**Índices Custom:**")
                    lines.append("| Ordem | Chave | Descrição |")
                    lines.append("|-------|-------|-----------|")
                    for i in t["indices_custom"]:
                        lines.append(f"| {i['ordem']} | `{i['chave']}` | {i['descricao']} |")

                # Custom triggers with new SX7 fields
                if t["gatilhos_custom"]:
                    lines.append(f"\n**Gatilhos Custom:**")
                    lines.append("| Origem | Destino | Regra | Condição |")
                    lines.append("|--------|---------|-------|----------|")
                    for g in t["gatilhos_custom"]:
                        cond = (g.get("condicao") or "")[:50]
                        lines.append(f"| `{g['campo_origem']}` | `{g['campo_destino']}` | `{g['regra']}` | `{cond}` |")

                # Standard field counts
                std = [c for c in t["campos"] if not c["custom"]]
                lines.append(f"\n*Campos padrão: {len(std)} | Índices total: {len(t['indices'])} | Gatilhos total: {len(t['gatilhos'])}*\n")

        # ── Section 4: Rotinas com Customizações ──
        if rotina_map:
            lines.append("## 4. Rotinas com Customizações\n")
            for rotina, info in sorted(rotina_map.items()):
                if rotina == "desconhecida":
                    continue
                lines.append(f"### {rotina}")

                # PEs
                if info["pes"]:
                    lines.append("\n**Pontos de Entrada:**")
                    lines.append("| PE | Fonte |")
                    lines.append("|----|-------|")
                    for pe in info["pes"]:
                        lines.append(f"| `{pe['pe']}` | {pe['fonte']} |")

                # Fontes linked to this rotina
                if info["fontes"]:
                    fontes_list = ", ".join("`" + fn + "`" for fn in sorted(info["fontes"]))
                    lines.append(f"\n**Fontes:** {fontes_list}")

                lines.append("")

            # Unknown PEs
            unknown = [v for v in v_pe_rotina if v["destino"] == "desconhecida"]
            if unknown:
                lines.append("### PEs sem rotina identificada\n")
                for v in unknown:
                    lines.append(f"- `{v['origem']}` (fonte: {v['contexto']})")
                lines.append("")

        # ── Section 6: Tipos e Classificações Custom (CBOX + SX5) ──
        # Collect all custom CBOX values across tables
        all_cbox = []
        if tables:
            for t in tables:
                for c in t["campos_custom"]:
                    if c.get("cbox"):
                        all_cbox.append((t["codigo"], c["campo"], c["titulo"], c["cbox"]))
        # SX5 generic tables
        sx5_ids = set()
        if tables:
            for t in tables:
                for c in t["campos"]:
                    ini = c.get("inicializador") or ""
                    val = c.get("validacao") or ""
                    for text in [ini, val]:
                        for m in re.findall(r'Pertence\("([^"]{2})"', text):
                            sx5_ids.add(m)
        sx5_data = self.get_tabelas_genericas(list(sx5_ids))
        sx5_custom = [s for s in sx5_data if s["custom"]]

        if all_cbox or sx5_custom:
            lines.append("## 6. Tipos e Classificações Custom\n")
            if all_cbox:
                lines.append("**CBox customizados:**")
                lines.append("| Tabela | Campo | Título | Valores |")
                lines.append("|--------|-------|--------|---------|")
                for tab, campo, titulo, cbox in all_cbox[:20]:
                    lines.append(f"| `{tab}` | `{campo}` | {titulo} | `{cbox[:60]}` |")
            if sx5_custom:
                lines.append("\n**Tabelas Genéricas Custom (SX5):**")
                lines.append("| Tabela | Chave | Descrição |")
                lines.append("|--------|-------|-----------|")
                for s in sx5_custom[:20]:
                    lines.append(f"| {s['tabela']} | {s['chave']} | {s['descricao']} |")
            lines.append("")

        # ── Section 7: Tabelas do Módulo (resumo) ──
        if tables:
            lines.append("## 7. Tabelas do Módulo\n")
            lines.append("| Tabela | Nome | Custom? | Campos | C.Custom | Índ.Custom | Gat.Custom |")
            lines.append("|--------|------|---------|--------|----------|------------|------------|")
            for t in tables:
                lines.append(
                    f"| `{t['codigo']}` | {t['nome'][:30]} | {'Sim' if t['custom'] else ''} "
                    f"| {len(t['campos'])} | {len(t['campos_custom'])} "
                    f"| {len(t['indices_custom'])} | {len(t['gatilhos_custom'])} |")
            lines.append("")

        # ── Section 9: Integrações ──
        if v_integracoes:
            lines.append("## 9. Integrações entre Módulos\n")
            for v in v_integracoes:
                lines.append(f"- `{v['origem']}` → `{v['destino']}` ({v['contexto']})")
            lines.append("")

        # ── Relationships map ──
        if rels:
            lines.append("## Relacionamentos entre Tabelas (SX9)\n")
            lines.append("| Origem | Destino | Expr Origem | Expr Destino | Custom |")
            lines.append("|--------|---------|-------------|-------------|--------|")
            for r in rels[:30]:
                tag = "Sim" if r["custom"] else ""
                lines.append(f"| `{r['tabela_origem']}` | `{r['tabela_destino']}` | `{r['expr_origem']}` | `{r['expr_destino']}` | {tag} |")
            lines.append("")

        # ── Section 15: Fontes Custom Detalhados ──
        if custom_fontes:
            lines.append("## 15. Fontes Custom\n")
            for f in custom_fontes:
                lines.append(f"### {f['arquivo']}")
                parts = []
                if f["funcoes"]:
                    parts.append(f"Funções: {', '.join(f['funcoes'][:10])}")
                if f["user_funcs"]:
                    parts.append(f"User Functions: {', '.join(f['user_funcs'][:10])}")
                if f["pontos_entrada"]:
                    parts.append(f"**PEs: {', '.join(f['pontos_entrada'])}**")
                if f["tabelas_ref"]:
                    parts.append(f"Tabelas: {', '.join(f['tabelas_ref'])}")
                lines.append("  " + " | ".join(parts))

                # Show which functions this fonte calls (from vinculos)
                calls = [v["destino"] for v in v_fonte_funcao if v["origem"] == f["arquivo"]]
                if calls:
                    lines.append(f"  Chama: {', '.join(calls[:10])}")

                # Show which tables it writes to
                writes = [v["destino"] for v in v_fonte_tabela_w if v["origem"] == f["arquivo"]]
                if writes:
                    lines.append(f"  Grava em: {', '.join(writes)}")

                lines.append("")

        # ── Section 16: Mapa de Vínculos ──
        has_vinculos = v_campo_funcao or v_gatilho_funcao or v_pe_rotina or v_fonte_funcao or v_campo_f3
        if has_vinculos:
            lines.append("## 16. Mapa de Vínculos\n")

            if v_campo_funcao:
                lines.append("### Campos → Funções (validação chama U_xxx)\n")
                lines.append("| Campo | Função | Tipo | Contexto |")
                lines.append("|-------|--------|------|----------|")
                for v in v_campo_funcao[:30]:
                    lines.append(f"| `{v['origem']}` | `{v['destino']}` | {v['origem_tipo']} | {v['contexto']} |")
                lines.append("")

            if v_gatilho_funcao:
                lines.append("### Gatilhos → Funções (regra chama U_xxx)\n")
                lines.append("| Gatilho | Função |")
                lines.append("|---------|--------|")
                for v in v_gatilho_funcao[:30]:
                    lines.append(f"| `{v['origem']}` | `{v['destino']}` |")
                lines.append("")

            if v_campo_f3:
                lines.append("### Campos → Tabelas (F3 consulta)\n")
                lines.append("| Campo | Tabela Consultada | Detalhe |")
                lines.append("|-------|-------------------|---------|")
                for v in v_campo_f3[:30]:
                    lines.append(f"| `{v['origem']}` | `{v['destino']}` | {v['contexto']} |")
                lines.append("")

            if v_fonte_funcao:
                lines.append("### Fonte → Função (call graph)\n")
                lines.append("| Fonte | Função Chamada |")
                lines.append("|-------|----------------|")
                for v in v_fonte_funcao[:40]:
                    lines.append(f"| `{v['origem']}` | `{v['destino']}` |")
                lines.append("")

        # ── Indices Custom (consolidated view) ──
        all_idx_custom = []
        if tables:
            for t in tables:
                for i in t["indices_custom"]:
                    all_idx_custom.append((t["codigo"], i))
        if all_idx_custom:
            lines.append("## Índices Custom (consolidado)\n")
            lines.append("| Tabela | Ordem | Chave | Descrição |")
            lines.append("|--------|-------|-------|-----------|")
            for tab, i in all_idx_custom:
                lines.append(f"| `{tab}` | {i['ordem']} | `{i['chave']}` | {i['descricao']} |")
            lines.append("")

        # ── Gatilhos com detalhes SX7 (all custom, consolidated) ──
        all_gat_custom = []
        if tables:
            for t in tables:
                for g in t["gatilhos_custom"]:
                    all_gat_custom.append((t["codigo"], g))
        if all_gat_custom:
            lines.append("## Gatilhos Custom (consolidado SX7)\n")
            lines.append("| Tabela | Origem | Destino | Regra | Condição |")
            lines.append("|--------|--------|---------|-------|----------|")
            for tab, g in all_gat_custom[:40]:
                cond = (g.get("condicao") or "")[:50]
                lines.append(f"| `{tab}` | `{g['campo_origem']}` | `{g['campo_destino']}` | `{g['regra'][:60]}` | `{cond}` |")
            lines.append("")

        # ── Truncation guard ──
        result = "\n".join(lines)
        if len(result) > 30000:
            result = result[:29900] + "\n\n> [TRUNCADO] Contexto excedeu 30.000 caracteres.\n"

        return result

    def build_deep_field_analysis(self, tabela: str) -> str:
        """Build a deep analysis of a specific table's fields for documentation."""
        info = self.get_table_info(tabela)
        if not info:
            return ""

        lines = [f"# Análise Detalhada: {tabela} — {info['nome']}\n"]

        # Group fields by prefix pattern to identify logical groups
        groups = {}
        for c in info["campos"]:
            campo = c["campo"]
            # Extract field prefix after table code (e.g., A1_NOME -> NOME)
            parts = campo.split("_", 1)
            suffix = parts[1] if len(parts) > 1 else campo
            if suffix.startswith("X"):
                groups.setdefault("CUSTOMIZADOS", []).append(c)
            else:
                groups.setdefault("PADRÃO", []).append(c)

        for group_name, fields in groups.items():
            lines.append(f"\n## Campos {group_name}\n")
            for c in fields:
                lines.append(f"### {c['campo']} — {c['titulo']}")
                lines.append(f"- **Descrição:** {c['descricao']}")
                lines.append(f"- **Tipo:** {c['tipo']} ({c['tamanho']},{c['decimal']})")
                lines.append(f"- **Obrigatório:** {'Sim' if c.get('obrigatorio') else 'Não'}")
                if c.get('validacao'):
                    lines.append(f"- **Validação:** `{c['validacao']}`")
                if c.get('inicializador'):
                    lines.append(f"- **Valor Padrão/Inicializador:** `{c['inicializador']}`")

                # Find triggers that affect this field
                triggers_to = [g for g in info["gatilhos"] if g["campo_destino"] == c["campo"]]
                triggers_from = [g for g in info["gatilhos"] if g["campo_origem"] == c["campo"]]
                if triggers_to:
                    lines.append(f"- **Preenchido por gatilho:**")
                    for g in triggers_to:
                        lines.append(f"  - Quando {g['campo_origem']} muda → Regra: `{g['regra']}`")
                if triggers_from:
                    lines.append(f"- **Dispara gatilho para:**")
                    for g in triggers_from:
                        lines.append(f"  - Preenche {g['campo_destino']} → Regra: `{g['regra']}`")

                lines.append("")

        # Relationships
        if info.get("relacionamentos_saida") or info.get("relacionamentos_entrada"):
            lines.append("\n## Relacionamentos\n")
            for r in info.get("relacionamentos_saida", []):
                lines.append(f"- → {r['tabela_destino']}: `{r['expr_origem']}` = `{r['expr_destino']}`")
            for r in info.get("relacionamentos_entrada", []):
                lines.append(f"- ← {r['tabela_origem']}: `{r['expr_origem']}` = `{r['expr_destino']}`")

        return "\n".join(lines)
