"""
Providers de LLM para o Agente Inteligente do BiizHubOps.

Suporta 10+ providers via 3 adaptadores:
- OpenAI-compatible (Ollama, OpenAI, Grok, DeepSeek, OpenRouter, Groq, Mistral, Together)
- Anthropic (Claude)
- Google (Gemini)

Sem dependências externas — usa apenas requests (já no projeto).
"""

import json
import logging
import os
import time
import random
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

# Timeout padrão para chamadas LLM (segundos)
DEFAULT_TIMEOUT = 60

# Timeout por provider — ajustado ao perfil de latência de cada um
PROVIDER_TIMEOUTS = {
    "ollama": 15,       # Local, deve responder rápido
    "groq": 20,         # Inferência acelerada
    "openai": 60,       # Cloud padrão
    "anthropic": 60,    # Cloud padrão
    "deepseek": 60,     # Cloud padrão
    "grok": 60,         # Cloud padrão
    "mistral": 60,      # Cloud padrão
    "together": 60,     # Cloud padrão
    "openrouter": 75,   # Gateway, pode adicionar latência
    "gemini": 90,       # Frequentemente mais lento
}

# Códigos de erro que devem ser retentados com backoff
_RETRIABLE_CODES = {"timeout", "rate_limit", "server_error"}

# Config de retry
_MAX_RETRIES = 3
_BASE_DELAY = 1.0  # segundos
_MAX_DELAY = 15.0  # segundos

# =================================================================
# REGISTRO DE PROVIDERS
# =================================================================

PROVIDERS = {
    "ollama": {
        "name": "Ollama (Local)",
        "adapter": "openai_compatible",
        "base_url": "http://localhost:11434",
        "api_path": "/api/chat",
        "requires_key": False,
        "default_model": "llama3.2:3b",
        "description": "Modelo local via Ollama. Sem custo, offline, privacidade total.",
        "supports_vision": False,
        "embedding": {"model": "mxbai-embed-large", "dims": 1024, "via": "ollama"},
        "models": [
            "llama3.2:1b",
            "llama3.2:3b",
            "llama3.1:8b",
            "llama3.3:70b",
            "gemma3:4b",
            "gemma3:12b",
            "qwen3:8b",
            "qwen3:14b",
            "deepseek-r1:7b",
            "deepseek-r1:14b",
            "phi-4:14b",
            "mistral:7b",
            "codellama:7b",
            "codellama:13b",
        ],
    },
    "openai": {
        "name": "OpenAI (GPT)",
        "adapter": "openai_compatible",
        "base_url": "https://api.openai.com",
        "api_path": "/v1/chat/completions",
        "requires_key": True,
        "default_model": "gpt-4o-mini",
        "description": "GPT-4o, GPT-4o-mini. Rápido e preciso.",
        "supports_vision": True,
        "embedding": {"model": "text-embedding-3-small", "dims": 1536, "via": "openai_compat"},
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "o3", "o3-mini", "o4-mini"],
    },
    "anthropic": {
        "name": "Anthropic (Claude)",
        "adapter": "anthropic",
        "base_url": "https://api.anthropic.com",
        "api_path": "/v1/messages",
        "requires_key": True,
        "default_model": "claude-sonnet-4-20250514",
        "description": "Claude Sonnet, Haiku, Opus. Excelente para análise técnica.",
        "supports_vision": True,
        "embedding": None,  # Anthropic nao tem API de embedding
        "models": ["claude-sonnet-4-20250514", "claude-haiku-4-5-20251001", "claude-opus-4-20250514"],
    },
    "gemini": {
        "name": "Google (Gemini)",
        "adapter": "google",
        "base_url": "https://generativelanguage.googleapis.com",
        "api_path": "/v1beta/models/{model}:generateContent",
        "requires_key": True,
        "default_model": "gemini-2.0-flash",
        "description": "Gemini Flash e Pro. Rápido, bom custo-benefício.",
        "supports_vision": True,
        "embedding": {"model": "text-embedding-004", "dims": 768, "via": "gemini"},
        "models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash", "gemini-2.0-flash-lite"],
    },
    "grok": {
        "name": "xAI (Grok)",
        "adapter": "openai_compatible",
        "base_url": "https://api.x.ai",
        "api_path": "/v1/chat/completions",
        "requires_key": True,
        "default_model": "grok-3-mini",
        "description": "Grok 3 da xAI. Bom para análise e raciocínio.",
        "supports_vision": True,
        "embedding": {"model": "v2-embedding", "dims": 1024, "via": "openai_compat"},
        "models": ["grok-3", "grok-3-fast", "grok-3-mini", "grok-3-mini-fast"],
    },
    "deepseek": {
        "name": "DeepSeek",
        "adapter": "openai_compatible",
        "base_url": "https://api.deepseek.com",
        "api_path": "/v1/chat/completions",
        "requires_key": True,
        "default_model": "deepseek-chat",
        "description": "DeepSeek Chat e Coder. Excelente para código, preço baixo.",
        "supports_vision": False,
        "embedding": None,  # DeepSeek nao oferece endpoint de embedding
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "openrouter": {
        "name": "OpenRouter",
        "adapter": "openai_compatible",
        "base_url": "https://openrouter.ai/api",
        "api_path": "/v1/chat/completions",
        "requires_key": True,
        "default_model": "meta-llama/llama-3.1-8b-instruct:free",
        "description": "Gateway para 100+ modelos. Alguns gratuitos.",
        "supports_vision": False,
        "embedding": {"model": "openai/text-embedding-3-small", "dims": 1536, "via": "openai_compat"},
        "models": [
            "anthropic/claude-sonnet-4",
            "google/gemini-2.5-flash",
            "openai/gpt-4o",
            "meta-llama/llama-3.3-70b-instruct",
            "deepseek/deepseek-chat",
            "deepseek/deepseek-reasoner",
            "qwen/qwen3-235b-a22b",
        ],
    },
    "groq": {
        "name": "Groq",
        "adapter": "openai_compatible",
        "base_url": "https://api.groq.com/openai",
        "api_path": "/v1/chat/completions",
        "requires_key": True,
        "default_model": "llama-3.3-70b-versatile",
        "description": "Inferência ultra-rápida. Modelos open-source acelerados.",
        "supports_vision": False,
        "embedding": None,  # Groq nao tem API de embedding
        "models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "gemma2-9b-it",
            "mistral-saba-24b",
            "qwen-qwq-32b",
        ],
    },
    "mistral": {
        "name": "Mistral AI",
        "adapter": "openai_compatible",
        "base_url": "https://api.mistral.ai",
        "api_path": "/v1/chat/completions",
        "requires_key": True,
        "default_model": "mistral-small-latest",
        "description": "Modelos Mistral e Mixtral. Bom para europeu/multilingual.",
        "supports_vision": False,
        "embedding": {"model": "mistral-embed", "dims": 1024, "via": "openai_compat"},
        "models": [
            "mistral-large-latest",
            "mistral-medium-latest",
            "mistral-small-latest",
            "codestral-latest",
            "open-mistral-nemo",
        ],
    },
    "together": {
        "name": "Together AI",
        "adapter": "openai_compatible",
        "base_url": "https://api.together.xyz",
        "api_path": "/v1/chat/completions",
        "requires_key": True,
        "default_model": "meta-llama/Llama-3.2-3B-Instruct-Turbo",
        "description": "Modelos open-source hospedados. Preço acessível.",
        "supports_vision": False,
        "embedding": {"model": "togethercomputer/m2-bert-80M-8k-retrieval", "dims": 768, "via": "openai_compat"},
        "models": [
            "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "deepseek-ai/DeepSeek-R1",
            "Qwen/Qwen2.5-72B-Instruct-Turbo",
            "mistralai/Mistral-Small-24B-Instruct-2501",
        ],
    },
}


def get_provider_list():
    """Retorna lista de providers disponíveis (sem dados sensíveis)."""
    result = []
    for pid, p in PROVIDERS.items():
        embed = p.get("embedding")
        entry = {
            "id": pid,
            "name": p["name"],
            "requires_key": p["requires_key"],
            "default_model": p["default_model"],
            "description": p["description"],
            "supports_vision": p.get("supports_vision", False),
            "supports_embedding": embed is not None,
            "embedding_model": embed["model"] if embed else None,
            "models": p.get("models", []),
        }
        result.append(entry)
    return result


# =================================================================
# CLASSE PRINCIPAL
# =================================================================


class LLMProvider:
    """Provider abstrato para chamadas LLM."""

    def __init__(self, provider_id, api_key=None, model=None, base_url=None, options=None):
        """
        Args:
            provider_id: ID do provider (ex: 'ollama', 'openai', 'anthropic')
            api_key: chave de API (None para Ollama)
            model: modelo a usar (None = default do provider)
            base_url: URL base customizada (None = default)
            options: dict com opções extras (temperature, max_tokens, num_ctx, etc.)
        """
        if provider_id not in PROVIDERS:
            raise ValueError(f"Provider desconhecido: {provider_id}. Disponíveis: {list(PROVIDERS.keys())}")

        self.provider_id = provider_id
        self.config = PROVIDERS[provider_id]
        self.api_key = api_key
        self.model = model or self.config["default_model"]
        self.base_url = base_url or self.config["base_url"]
        self.supports_vision = self.config.get("supports_vision", False)
        self.options = options or {}
        self.adapter = self.config["adapter"]

    def chat(self, messages, system_prompt=None, temperature=0.7, max_tokens=2048):
        """Envia mensagens para o LLM e retorna a resposta.

        Inclui retry automático com backoff exponencial + jitter para erros
        transientes (timeout, rate_limit, server_error). Erros de autenticação
        e API não são retentados.

        Args:
            messages: lista de dicts [{"role": "user", "content": "..."}]
            system_prompt: prompt de sistema (contexto do agente)
            temperature: criatividade (0.0 = determinístico, 1.0 = criativo)
            max_tokens: máximo de tokens na resposta

        Returns:
            dict: {"content": "resposta", "model": "modelo usado",
                   "usage": {"prompt_tokens": N, "completion_tokens": N},
                   "provider": "provider_id"}

        Raises:
            LLMError: erro na chamada (timeout, auth, rate limit, etc.)
        """
        # Merge opções
        temp = self.options.get("temperature", temperature)
        tokens = self.options.get("max_tokens", max_tokens)

        last_error = None
        max_retries = int(self.options.get("max_retries", _MAX_RETRIES))

        for attempt in range(max_retries):
            try:
                # Dispatch por adaptador
                if self.adapter == "openai_compatible":
                    return self._chat_openai(messages, system_prompt, temp, tokens)
                elif self.adapter == "anthropic":
                    return self._chat_anthropic(messages, system_prompt, temp, tokens)
                elif self.adapter == "google":
                    return self._chat_google(messages, system_prompt, temp, tokens)
                else:
                    raise LLMError(f"Adaptador desconhecido: {self.adapter}")
            except LLMError as e:
                last_error = e
                # Só retenta erros transientes
                if e.code not in _RETRIABLE_CODES or attempt >= max_retries - 1:
                    raise

                # Backoff exponencial com jitter
                delay = min(_BASE_DELAY * (2 ** attempt) + random.uniform(0, 1), _MAX_DELAY)
                logger.warning(
                    "LLM %s tentativa %d/%d falhou (%s): %s — retentando em %.1fs",
                    self.provider_id, attempt + 1, max_retries, e.code, str(e)[:100], delay
                )
                time.sleep(delay)

        raise last_error

    def chat_stream(self, messages, system_prompt=None, temperature=0.7, max_tokens=2048):
        """Envia mensagens para o LLM e retorna generator de chunks (streaming).

        Cada chunk é um dict: {"chunk": "texto parcial", "done": False}
        O último chunk inclui {"done": True, "usage": {...}, "model": "..."}

        Sem retry automático — streaming não é idempotente.
        Fallback para chat() se o adapter não suporta streaming.

        Yields:
            dict: {"chunk": str, "done": bool, ...}
        """
        temp = self.options.get("temperature", temperature)
        tokens = self.options.get("max_tokens", max_tokens)

        if self.adapter == "openai_compatible":
            yield from self._stream_openai(messages, system_prompt, temp, tokens)
        elif self.adapter == "anthropic":
            yield from self._stream_anthropic(messages, system_prompt, temp, tokens)
        elif self.adapter == "google":
            # Gemini streaming tem formato diferente — fallback para blocking
            result = self.chat(messages, system_prompt, temperature, max_tokens)
            yield {"chunk": result["content"], "done": True,
                   "model": result.get("model", self.model),
                   "usage": result.get("usage", {}), "provider": self.provider_id}
        else:
            raise LLMError(f"Adaptador desconhecido: {self.adapter}")

    def _stream_openai(self, messages, system_prompt, temperature, max_tokens):
        """Streaming para APIs OpenAI-compatible (Ollama, GPT, Grok, DeepSeek, etc.)."""
        url = f"{self.base_url}{self.config['api_path']}"

        api_messages = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})
        api_messages.extend(messages)

        if self.provider_id == "ollama":
            body = {
                "model": self.model,
                "messages": api_messages,
                "stream": True,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    "num_ctx": self.options.get("num_ctx", 2048),
                },
            }
        else:
            body = {
                "model": self.model,
                "messages": api_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            }

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.provider_id == "openrouter":
            headers["HTTP-Referer"] = "https://atudic.dev"
            headers["X-Title"] = "BiizHubOps Agent"

        try:
            timeout = self.options.get("timeout", PROVIDER_TIMEOUTS.get(self.provider_id, DEFAULT_TIMEOUT))
            resp = requests.post(url, json=body, headers=headers, timeout=timeout, stream=True)

            if resp.status_code == 401:
                raise LLMError("Chave de API inválida ou expirada", code="auth_error")
            elif resp.status_code == 429:
                raise LLMError("Rate limit excedido", code="rate_limit")
            elif resp.status_code >= 500:
                raise LLMError(f"Erro no servidor ({resp.status_code})", code="server_error")
            elif resp.status_code != 200:
                raise LLMError(f"Erro {resp.status_code}: {resp.text[:200]}", code="api_error")

            full_content = []
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue

                # Ollama retorna JSON por linha (sem prefixo "data: ")
                if self.provider_id == "ollama":
                    try:
                        data = json.loads(line)
                        chunk = data.get("message", {}).get("content", "")
                        done = data.get("done", False)
                        if chunk:
                            full_content.append(chunk)
                            yield {"chunk": chunk, "done": False}
                        if done:
                            yield {
                                "chunk": "", "done": True,
                                "model": data.get("model", self.model),
                                "usage": {
                                    "prompt_tokens": data.get("prompt_eval_count", 0),
                                    "completion_tokens": data.get("eval_count", 0),
                                },
                                "provider": self.provider_id,
                                "content": "".join(full_content),
                            }
                            return
                    except json.JSONDecodeError:
                        continue
                else:
                    # OpenAI SSE: "data: {...}" ou "data: [DONE]"
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        yield {
                            "chunk": "", "done": True,
                            "model": self.model,
                            "usage": {},
                            "provider": self.provider_id,
                            "content": "".join(full_content),
                        }
                        return
                    try:
                        data = json.loads(payload)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        chunk = delta.get("content", "")
                        if chunk:
                            full_content.append(chunk)
                            yield {"chunk": chunk, "done": False}
                    except json.JSONDecodeError:
                        continue

            # Se o loop terminou sem [DONE] (raro)
            yield {
                "chunk": "", "done": True,
                "model": self.model,
                "usage": {},
                "provider": self.provider_id,
                "content": "".join(full_content),
            }

        except requests.exceptions.Timeout:
            raise LLMError("Timeout na chamada LLM streaming", code="timeout")
        except requests.exceptions.ConnectionError:
            raise LLMError(f"Não foi possível conectar a {self.base_url}", code="connection_error")

    def _stream_anthropic(self, messages, system_prompt, temperature, max_tokens):
        """Streaming para API Anthropic (Claude) via SSE."""
        url = f"{self.base_url}{self.config['api_path']}"

        api_messages = []
        for msg in messages:
            content = msg["content"]
            if isinstance(content, list):
                anthropic_content = []
                for item in content:
                    if item.get("type") == "text":
                        anthropic_content.append({"type": "text", "text": item["text"]})
                    elif item.get("type") == "image_url":
                        img_url = item["image_url"]["url"]
                        if img_url.startswith("data:"):
                            mime_end = img_url.index(";")
                            media_type = img_url[5:mime_end]
                            b64_data = img_url.split(",", 1)[1]
                            anthropic_content.append({
                                "type": "image",
                                "source": {"type": "base64", "media_type": media_type, "data": b64_data},
                            })
                api_messages.append({"role": msg["role"], "content": anthropic_content})
            else:
                api_messages.append(msg)

        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": api_messages,
            "stream": True,
        }
        if system_prompt:
            body["system"] = system_prompt
        if temperature is not None:
            body["temperature"] = temperature

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key or "",
            "anthropic-version": "2023-06-01",
        }

        try:
            timeout = self.options.get("timeout", PROVIDER_TIMEOUTS.get(self.provider_id, DEFAULT_TIMEOUT))
            resp = requests.post(url, json=body, headers=headers, timeout=timeout, stream=True)

            if resp.status_code == 401:
                raise LLMError("Chave de API Anthropic inválida", code="auth_error")
            elif resp.status_code == 429:
                raise LLMError("Rate limit Anthropic excedido", code="rate_limit")
            elif resp.status_code >= 400:
                raise LLMError(f"Erro Anthropic {resp.status_code}", code="api_error")

            full_content = []
            usage = {}
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                payload = line[6:]
                try:
                    data = json.loads(payload)
                    event_type = data.get("type", "")

                    if event_type == "content_block_delta":
                        chunk = data.get("delta", {}).get("text", "")
                        if chunk:
                            full_content.append(chunk)
                            yield {"chunk": chunk, "done": False}

                    elif event_type == "message_delta":
                        usage = data.get("usage", {})

                    elif event_type == "message_stop":
                        yield {
                            "chunk": "", "done": True,
                            "model": self.model,
                            "usage": usage,
                            "provider": self.provider_id,
                            "content": "".join(full_content),
                        }
                        return
                except json.JSONDecodeError:
                    continue

            yield {
                "chunk": "", "done": True,
                "model": self.model,
                "usage": usage,
                "provider": self.provider_id,
                "content": "".join(full_content),
            }

        except requests.exceptions.Timeout:
            raise LLMError("Timeout na chamada Claude streaming", code="timeout")
        except requests.exceptions.ConnectionError:
            raise LLMError("Não foi possível conectar à API Anthropic", code="connection_error")

    def test_connection(self):
        """Testa conexão com o provider. Retorna True/False + mensagem."""
        try:
            if self.provider_id == "ollama":
                resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
                if resp.status_code == 200:
                    models = [m["name"] for m in resp.json().get("models", [])]
                    return True, f"Conectado. Modelos: {', '.join(models[:5])}"
                return False, f"Erro {resp.status_code}"
            else:
                # Para APIs externas, faz uma chamada mínima
                result = self.chat([{"role": "user", "content": "Responda apenas: ok"}], max_tokens=5)
                return True, f"Conectado. Modelo: {result.get('model', '?')}"
        except LLMError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Erro de conexão: {str(e)}"

    # =================================================================
    # EMBEDDINGS
    # =================================================================

    def get_embedding(self, text, model=None):
        """Gera embedding vetorial para um texto.

        Cada provider tem seu modelo e endpoint de embedding configurado
        no campo 'embedding' do PROVIDERS. Providers sem embedding (Anthropic,
        Groq, DeepSeek) retornam None — o sistema faz fallback automatico
        para outro provider que tenha.

        Args:
            text: texto para embedar
            model: modelo de embedding (None = default do provider)
        """
        embed_cfg = self.config.get("embedding")
        if not embed_cfg:
            return None

        via = embed_cfg["via"]
        embed_model = model or embed_cfg["model"]

        try:
            if via == "ollama":
                return self._embedding_ollama(text, embed_model)
            elif via == "gemini":
                return self._embedding_gemini(text, embed_model)
            elif via == "openai_compat":
                return self._embedding_openai(text, embed_model)
            else:
                return None
        except Exception as e:
            logger.warning("Erro ao gerar embedding via %s: %s", self.provider_id, e)
            return None

    def get_embeddings_batch(self, texts, model=None):
        """Gera embeddings para multiplos textos em uma unica chamada.

        Reduz latencia e overhead de rede. Providers OpenAI-compatible
        aceitam lista no campo 'input'. Gemini e Ollama fazem N chamadas.

        Args:
            texts: lista de textos para embedar
            model: modelo de embedding (None = default)

        Returns:
            list: lista de embeddings (mesmo indice que texts). None para falhas.
        """
        if not texts:
            return []

        embed_cfg = self.config.get("embedding")
        if not embed_cfg:
            return [None] * len(texts)

        via = embed_cfg["via"]
        embed_model = model or embed_cfg["model"]

        # OpenAI-compatible suporta batch nativo (lista no campo input)
        if via == "openai_compat":
            return self._embedding_openai_batch(texts, embed_model)

        # Demais: fallback para chamadas individuais
        results = []
        for text in texts:
            try:
                emb = self.get_embedding(text, model)
                results.append(emb)
            except Exception:
                results.append(None)
        return results

    def _embedding_openai_batch(self, texts, model):
        """Batch embedding via OpenAI-compatible API (1 chamada para N textos)."""
        url = f"{self.base_url}/v1/embeddings"

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        body = {"model": model, "input": texts}

        try:
            resp = requests.post(url, json=body, headers=headers, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                embeddings_data = data.get("data", [])
                # Garantir ordem correta (API retorna com index)
                result = [None] * len(texts)
                for item in embeddings_data:
                    idx = item.get("index", 0)
                    if idx < len(result):
                        result[idx] = item.get("embedding")
                return result
        except Exception as e:
            logger.warning("Batch embedding falhou via %s: %s", self.provider_id, e)

        # Fallback: chamadas individuais
        return [self.get_embedding(t, model) for t in texts]

    def _embedding_ollama(self, text, model=None):
        """Embedding via Ollama — tenta /api/embed (v2) e fallback /api/embeddings (v1)."""
        embed_model = model or os.environ.get("OLLAMA_EMBED_MODEL") or "mxbai-embed-large"

        # Ollama v0.4+ usa /api/embed; versoes anteriores usam /api/embeddings
        endpoints = [
            (f"{self.base_url}/api/embed", {"model": embed_model, "input": text}),
            (f"{self.base_url}/api/embeddings", {"model": embed_model, "prompt": text}),
        ]

        for url, body in endpoints:
            try:
                resp = requests.post(url, json=body, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    # /api/embed retorna "embeddings", /api/embeddings retorna "embedding"
                    embedding = data.get("embeddings", [None])[0] if "embeddings" in data else data.get("embedding")
                    if embedding:
                        return embedding
            except requests.RequestException:
                continue

        logger.warning(
            "Ollama embedding falhou para modelo '%s' — verifique se o modelo esta instalado: ollama pull %s",
            embed_model, embed_model,
        )
        return None

    def _embedding_openai(self, text, model=None):
        """Embedding via API OpenAI-compatible (/v1/embeddings)."""
        embed_model = model or "text-embedding-3-small"
        url = f"{self.base_url}/v1/embeddings"

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        body = {"model": embed_model, "input": text}

        resp = requests.post(url, json=body, headers=headers, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            embeddings = data.get("data", [])
            if embeddings:
                return embeddings[0].get("embedding")
        logger.warning("%s embedding falhou: %d", self.provider_id, resp.status_code)
        return None

    def _embedding_gemini(self, text, model=None):
        """Embedding via Google Gemini API."""
        embed_model = model or "text-embedding-004"
        url = (
            f"{self.base_url}/v1beta/models/{embed_model}:embedContent"
            f"?key={self.api_key}"
        )

        body = {
            "model": f"models/{embed_model}",
            "content": {"parts": [{"text": text}]},
        }

        resp = requests.post(url, json=body, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            embedding = data.get("embedding", {}).get("values")
            if embedding:
                return embedding
        logger.warning("Gemini embedding falhou: %d", resp.status_code)
        return None

    @property
    def supports_embedding(self):
        """Verifica se o provider suporta embeddings (baseado na config)."""
        return self.config.get("embedding") is not None

    @property
    def embedding_info(self):
        """Retorna info do embedding do provider (modelo, dimensoes) ou None."""
        return self.config.get("embedding")

    # =================================================================
    # ADAPTADOR: OPENAI-COMPATIBLE
    # =================================================================

    def _chat_openai(self, messages, system_prompt, temperature, max_tokens):
        """Chamada para APIs no formato OpenAI (Ollama, GPT, Grok, DeepSeek, etc.)."""
        url = f"{self.base_url}{self.config['api_path']}"

        # Montar mensagens com system prompt
        api_messages = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})
        api_messages.extend(messages)

        # Body padrão OpenAI
        body = {
            "model": self.model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        # Ollama usa formato levemente diferente
        if self.provider_id == "ollama":
            # Ollama /api/chat
            body = {
                "model": self.model,
                "messages": api_messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    "num_ctx": self.options.get("num_ctx", 2048),
                },
            }

        # Headers
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # OpenRouter precisa de headers extras
        if self.provider_id == "openrouter":
            headers["HTTP-Referer"] = "https://atudic.dev"
            headers["X-Title"] = "BiizHubOps Agent"

        try:
            timeout = self.options.get("timeout", PROVIDER_TIMEOUTS.get(self.provider_id, DEFAULT_TIMEOUT))
            resp = requests.post(url, json=body, headers=headers, timeout=timeout)

            if resp.status_code == 401:
                raise LLMError("Chave de API inválida ou expirada", code="auth_error")
            elif resp.status_code == 429:
                raise LLMError("Rate limit excedido. Aguarde e tente novamente.", code="rate_limit")
            elif resp.status_code >= 500:
                raise LLMError(f"Erro no servidor do provider ({resp.status_code})", code="server_error")
            elif resp.status_code != 200:
                detail = resp.text[:200]
                raise LLMError(f"Erro {resp.status_code}: {detail}", code="api_error")

            data = resp.json()

            # Extrair resposta — Ollama vs OpenAI format
            if self.provider_id == "ollama":
                content = data.get("message", {}).get("content", "")
                usage = {
                    "prompt_tokens": data.get("prompt_eval_count", 0),
                    "completion_tokens": data.get("eval_count", 0),
                }
            else:
                choice = data.get("choices", [{}])[0]
                content = choice.get("message", {}).get("content", "")
                usage = data.get("usage", {})

            return {
                "content": content,
                "model": data.get("model", self.model),
                "usage": usage,
                "provider": self.provider_id,
            }

        except requests.exceptions.Timeout:
            raise LLMError("Timeout na chamada LLM. Tente um modelo menor.", code="timeout")
        except requests.exceptions.ConnectionError:
            raise LLMError(
                f"Não foi possível conectar a {self.base_url}. Verifique se o serviço está rodando.",
                code="connection_error",
            )

    # =================================================================
    # ADAPTADOR: ANTHROPIC (CLAUDE)
    # =================================================================

    def _chat_anthropic(self, messages, system_prompt, temperature, max_tokens):
        """Chamada para a API da Anthropic (Claude)."""
        url = f"{self.base_url}{self.config['api_path']}"

        # Anthropic usa formato próprio — converter imagens para formato Anthropic
        api_messages = []
        for msg in messages:
            content = msg["content"]
            if isinstance(content, list):
                # Multimodal: converter image_url para formato Anthropic
                anthropic_content = []
                for item in content:
                    if item.get("type") == "text":
                        anthropic_content.append({"type": "text", "text": item["text"]})
                    elif item.get("type") == "image_url":
                        img_url = item["image_url"]["url"]
                        if img_url.startswith("data:"):
                            mime_end = img_url.index(";")
                            media_type = img_url[5:mime_end]
                            b64_data = img_url.split(",", 1)[1]
                            anthropic_content.append(
                                {
                                    "type": "image",
                                    "source": {"type": "base64", "media_type": media_type, "data": b64_data},
                                }
                            )
                api_messages.append({"role": msg["role"], "content": anthropic_content})
            else:
                api_messages.append(msg)

        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": api_messages,
        }

        if system_prompt:
            body["system"] = system_prompt

        if temperature is not None:
            body["temperature"] = temperature

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key or "",
            "anthropic-version": "2023-06-01",
        }

        try:
            timeout = self.options.get("timeout", PROVIDER_TIMEOUTS.get(self.provider_id, DEFAULT_TIMEOUT))
            resp = requests.post(url, json=body, headers=headers, timeout=timeout)

            if resp.status_code == 401:
                raise LLMError("Chave de API Anthropic inválida", code="auth_error")
            elif resp.status_code == 429:
                raise LLMError("Rate limit Anthropic excedido", code="rate_limit")
            elif resp.status_code == 529:
                raise LLMError("Anthropic sobrecarregada (529) — retentando", code="server_error")
            elif resp.status_code >= 500:
                detail = resp.json().get("error", {}).get("message", resp.text[:200])
                raise LLMError(f"Erro servidor Anthropic: {detail}", code="server_error")
            elif resp.status_code >= 400:
                detail = resp.json().get("error", {}).get("message", resp.text[:200])
                raise LLMError(f"Erro Anthropic: {detail}", code="api_error")

            data = resp.json()
            content_blocks = data.get("content", [])
            content = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")

            return {
                "content": content,
                "model": data.get("model", self.model),
                "usage": data.get("usage", {}),
                "provider": self.provider_id,
            }

        except requests.exceptions.Timeout:
            raise LLMError("Timeout na chamada Claude", code="timeout")
        except requests.exceptions.ConnectionError:
            raise LLMError("Não foi possível conectar à API Anthropic", code="connection_error")

    # =================================================================
    # ADAPTADOR: GOOGLE (GEMINI)
    # =================================================================

    def _chat_google(self, messages, system_prompt, temperature, max_tokens):
        """Chamada para a API do Google Gemini."""
        # Gemini usa modelo na URL
        api_path = self.config["api_path"].replace("{model}", self.model)
        url = f"{self.base_url}{api_path}?key={self.api_key or ''}"

        # Converter mensagens para formato Gemini
        contents = []
        system_instruction = None
        if system_prompt:
            # Gemini 1.5+ suporta systemInstruction nativo (melhor que user/model hack)
            system_instruction = {"parts": [{"text": system_prompt}]}

        for msg in messages:
            role = "model" if msg["role"] == "assistant" else "user"
            content = msg["content"]

            # Suporte multimodal (imagens)
            if isinstance(content, list):
                parts = []
                for item in content:
                    if item.get("type") == "text":
                        parts.append({"text": item["text"]})
                    elif item.get("type") == "image_url":
                        # Extrair base64 do data URL
                        img_url = item["image_url"]["url"]
                        if img_url.startswith("data:"):
                            mime_end = img_url.index(";")
                            mime_type = img_url[5:mime_end]
                            b64_data = img_url.split(",", 1)[1]
                            parts.append({"inlineData": {"mimeType": mime_type, "data": b64_data}})
                contents.append({"role": role, "parts": parts})
            else:
                contents.append({"role": role, "parts": [{"text": content}]})

        body = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system_instruction:
            body["systemInstruction"] = system_instruction

        headers = {"Content-Type": "application/json"}

        try:
            timeout = self.options.get("timeout", PROVIDER_TIMEOUTS.get(self.provider_id, DEFAULT_TIMEOUT))
            resp = requests.post(url, json=body, headers=headers, timeout=timeout)

            if resp.status_code == 400:
                detail = resp.json().get("error", {}).get("message", "")
                raise LLMError(f"Erro Gemini: {detail}", code="api_error")
            elif resp.status_code == 403:
                raise LLMError("Chave de API Gemini inválida ou sem permissão", code="auth_error")
            elif resp.status_code == 429:
                raise LLMError("Rate limit Gemini excedido", code="rate_limit")
            elif resp.status_code >= 400:
                raise LLMError(f"Erro Gemini {resp.status_code}: {resp.text[:200]}", code="api_error")

            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise LLMError("Gemini retornou resposta vazia", code="empty_response")

            parts = candidates[0].get("content", {}).get("parts", [])
            content = "".join(p.get("text", "") for p in parts)

            usage_meta = data.get("usageMetadata", {})
            return {
                "content": content,
                "model": self.model,
                "usage": {
                    "prompt_tokens": usage_meta.get("promptTokenCount", 0),
                    "completion_tokens": usage_meta.get("candidatesTokenCount", 0),
                },
                "provider": self.provider_id,
            }

        except requests.exceptions.Timeout:
            raise LLMError("Timeout na chamada Gemini", code="timeout")
        except requests.exceptions.ConnectionError:
            raise LLMError("Não foi possível conectar à API Gemini", code="connection_error")


# =================================================================
# EXCEÇÃO CUSTOMIZADA
# =================================================================


class LLMError(Exception):
    """Erro em chamada LLM."""

    def __init__(self, message, code="unknown"):
        super().__init__(message)
        self.code = code


# =================================================================
# FACTORY — CRIAR PROVIDER A PARTIR DE CONFIG DO BANCO
# =================================================================


def create_provider_from_config(config):
    """Cria LLMProvider a partir de config do banco (dict).

    Args:
        config: dict com {provider_id, api_key, model, base_url, options}

    Returns:
        LLMProvider
    """
    options = config.get("options", {})
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except (json.JSONDecodeError, TypeError):
            options = {}

    return LLMProvider(
        provider_id=config["provider_id"],
        api_key=config.get("api_key"),
        model=config.get("model"),
        base_url=config.get("base_url"),
        options=options,
    )
