"""Verification + Reflection — anti-hallucination layer.

Before streaming the final answer, this module:
1. Generates a draft response (non-streaming, cheap model)
2. Verifies each claim against the investigation context
3. Removes ungrounded claims, flags gaps
4. Reflects on answer quality
"""
import json
import asyncio
from typing import Optional


DRAFT_PROMPT = """Voce e um analista tecnico Protheus. Com base EXCLUSIVAMENTE nos dados abaixo,
gere uma resposta COMPLETA para a pergunta do usuario.

REGRA CRITICA: Use APENAS informacoes presentes no contexto. NAO invente dados.
Para cada afirmacao importante, indique a fonte entre colchetes: [FONTE: nome_da_ferramenta]

PERGUNTA: {message}
MODO: {modo}

CONTEXTO DA INVESTIGACAO:
{context}

Gere a resposta completa. Seja preciso e fundamentado."""


VERIFY_PROMPT = """Voce e um verificador de qualidade. Analise o RASCUNHO de resposta abaixo
e verifique se cada afirmacao tem base no CONTEXTO fornecido.

CONTEXTO DA INVESTIGACAO:
{context}

RASCUNHO DA RESPOSTA:
{draft}

INSTRUCOES:
1. Para cada afirmacao factual no rascunho, verifique se existe evidencia no contexto
2. Liste afirmacoes SEM base (inventadas ou nao encontradas no contexto)
3. Identifique dados que faltam (perguntas que deveriam ter sido respondidas mas nao foram)
4. De uma nota de confianca (0.0 a 1.0)

Responda APENAS com JSON:
{{
  "claims_verificados": ["afirmacao 1 que tem base", "afirmacao 2 que tem base"],
  "claims_sem_base": ["afirmacao inventada 1", "afirmacao sem evidencia 2"],
  "dados_faltando": ["dado 1 que deveria ter sido investigado", "dado 2"],
  "confianca": 0.85,
  "sugestao_correcao": "Remover afirmacao X. Adicionar ressalva sobre Y."
}}"""


REFLECT_PROMPT = """Revise rapidamente esta resposta tecnica sobre Protheus:

PERGUNTA ORIGINAL: {message}
MODO: {modo}
RESPOSTA: {answer}

Verifique:
1. Respondemos o que o usuario REALMENTE perguntou?
2. {mode_check}
3. A resposta e pratica e acionavel?

Se a resposta esta boa, responda "OK".
Se precisa de ajuste, responda com o texto a ADICIONAR no final (nao repita a resposta inteira).
Maximo 3 frases."""

_MODE_CHECKS = {
    "ajuste": "Identificamos a CAUSA RAIZ ou so os sintomas? Se so sintomas, que dado falta?",
    "melhoria": "Listamos TODOS os pontos de impacto? Faltou algum artefato?",
    "duvida": "A explicacao e clara e completa? Tem algo ambiguo?",
}


async def verify_and_reflect(
    llm,
    investigation_context: str,
    message: str,
    modo: str,
) -> dict:
    """Generate, verify, and reflect on the response.

    Returns:
        {
            "verified_draft": str,   # Corrected response ready for streaming
            "confidence": float,     # 0.0-1.0
            "gaps": list[str],       # What data is missing
            "reflection": str,       # Quality reflection note
        }
    """
    # ── Step 1: Generate draft ────────────────────────────────────────────
    draft_prompt = DRAFT_PROMPT.format(
        message=message,
        modo=modo,
        context=investigation_context[:12000],
    )

    try:
        draft = await asyncio.to_thread(
            llm._call,
            [{"role": "user", "content": draft_prompt}],
            temperature=0.3,
            use_gen=True,
            timeout=45,
        )
    except Exception as e:
        # If draft generation fails, return empty — caller will use normal flow
        return {
            "verified_draft": "",
            "confidence": 0.0,
            "gaps": [f"Erro ao gerar draft: {str(e)[:100]}"],
            "reflection": "",
        }

    if not draft or len(draft.strip()) < 50:
        return {"verified_draft": "", "confidence": 0.0, "gaps": ["Draft vazio"], "reflection": ""}

    # ── Step 2: Verify claims ─────────────────────────────────────────────
    verify_prompt = VERIFY_PROMPT.format(
        context=investigation_context[:8000],
        draft=draft[:4000],
    )

    verification = {"claims_sem_base": [], "dados_faltando": [], "confianca": 0.8, "sugestao_correcao": ""}
    try:
        verify_response = await asyncio.to_thread(
            llm._call,
            [{"role": "user", "content": verify_prompt}],
            temperature=0.1,
            use_gen=True,
            timeout=30,
        )

        # Parse JSON
        text = verify_response.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        verification = json.loads(text)
    except Exception:
        pass  # Use defaults — don't block on verification failure

    confidence = verification.get("confianca", 0.8)
    claims_sem_base = verification.get("claims_sem_base", [])
    dados_faltando = verification.get("dados_faltando", [])
    sugestao = verification.get("sugestao_correcao", "")

    # ── Step 3: Correct draft if needed ───────────────────────────────────
    corrected_draft = draft
    if claims_sem_base and confidence < 0.9:
        # Add warning about unverified claims
        warning = "\n\n> **Nota**: Algumas informações não puderam ser verificadas nos dados disponíveis"
        if dados_faltando:
            warning += ":\n" + "\n".join(f"> - {d}" for d in dados_faltando[:3])
        corrected_draft = draft + warning

    # ── Step 4: Quick reflection ──────────────────────────────────────────
    reflection = ""
    try:
        mode_check = _MODE_CHECKS.get(modo, "A resposta é adequada?")
        reflect_prompt = REFLECT_PROMPT.format(
            message=message,
            modo=modo,
            answer=corrected_draft[:3000],
            mode_check=mode_check,
        )

        reflect_response = await asyncio.to_thread(
            llm._call,
            [{"role": "user", "content": reflect_prompt}],
            temperature=0.1,
            use_gen=True,
            timeout=15,
        )

        if reflect_response and reflect_response.strip().upper() != "OK":
            reflection = reflect_response.strip()
            # Append reflection as addendum if it's short and useful
            if len(reflection) < 300 and not reflection.upper().startswith("OK"):
                corrected_draft += f"\n\n---\n{reflection}"
    except Exception:
        pass

    return {
        "verified_draft": corrected_draft,
        "confidence": confidence,
        "gaps": dados_faltando,
        "reflection": reflection,
    }


def should_verify(modo: str, tool_result_count: int, confidence_hint: float = 1.0, context: str = "") -> bool:
    """Decide whether verification should run.

    Rules:
    - ajuste mode: ALWAYS (accuracy is critical for debugging)
    - melhoria mode: when 3+ tool results OR context has critical risks (MsExecAuto)
    - duvida mode: when confidence < 0.7 (uncertain context)
    """
    if modo == "ajuste":
        return True
    if modo == "melhoria" and tool_result_count >= 3:
        return True
    if modo == "melhoria" and "MsExecAuto" in context:
        return True  # Critical risk detected — must verify
    if confidence_hint < 0.7:
        return True
    return False
