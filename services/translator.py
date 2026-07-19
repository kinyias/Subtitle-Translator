"""AI-powered subtitle translation.

Translates subtitle **text only**, one segment in -> one segment out, so the
original ``start_time`` / ``end_time`` of every cue is preserved exactly. The
model never sees or returns timing information; we send an indexed list of
strings and map the response back by index.

The endpoint is any OpenAI-compatible ``/chat/completions`` service (OpenAI,
OpenRouter, Groq, LM Studio, Ollama's OpenAI shim, ...). Only ``requests`` is
required.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from services import capcut_api  # reuse its bundled ``requests`` import
from services.base import ServiceError

# Translate in batches so a single request stays small and robust. Order is
# always preserved and every batch is re-checked against its inputs. Kept modest
# because reasoning models spend output tokens on their thinking, leaving fewer
# for the JSON reply; oversized batches get truncated mid-array.
_BATCH_SIZE = 20

# Smallest sub-batch used when retrying lines the model dropped/truncated. A
# batch that still fails to translate at size 1 falls back to the source text.
_MIN_BATCH_SIZE = 1

# Requested output-token ceiling. Large so a full batch's JSON fits alongside
# any reasoning tokens. Sent as both keys since servers differ on which they
# honour; stripped automatically if the endpoint rejects them.
_MAX_TOKENS = 8192

_SYSTEM_PROMPT = (
    "You are a professional subtitle translator. You receive a JSON array of "
    "subtitle lines, each an object with an integer \"id\" and a \"text\". "
    "Translate ONLY the value of \"text\" into the requested target language. "
    "Return a JSON object of the form {\"items\":[{\"id\":<same id>,\"text\":"
    "\"<translation>\"}]} with EXACTLY one entry per input id and the same ids. "
    "Never merge, split, reorder, add or drop lines - the count must match. "
    "Do not add timestamps, numbering, quotes or commentary. Preserve meaningful "
    "line breaks within a subtitle. If a line is empty or untranslatable, return "
    "it unchanged. Output ONLY the raw JSON object - no markdown fences, no "
    "reasoning, no <thinking> block, nothing before or after the JSON."
)


@dataclass
class TranslatorConfig:
    """Connection + style settings for the translation endpoint."""

    base_url: str = "http://localhost:20128/v1/chat/completions"
    api_key: str = ""
    model: str = "openai/gpt-5"
    target_language: str = "Vietnamese"
    style_prompt: str = ""
    # ``None`` omits ``temperature`` from the request entirely. Reasoning models
    # (e.g. gpt-5) only accept their default and reject any explicit value, so
    # leaving it unset is the safe default.
    temperature: Optional[float] = None

    def validated(self) -> "TranslatorConfig":
        if not self.base_url.strip():
            raise ServiceError("AI endpoint URL is required.")
        if not self.model.strip():
            raise ServiceError("AI model name is required.")
        return self


class Translator:
    """Calls an OpenAI-compatible chat endpoint to translate subtitle text."""

    def __init__(self, timeout: int = 120) -> None:
        self.timeout = timeout

    def translate_segments(
        self,
        texts: List[str],
        config: TranslatorConfig,
        logger: Optional[Any] = None,
    ) -> List[str]:
        """Return a translated string for each input string, order preserved.

        The returned list has the same length as *texts*; on any per-batch
        failure a :class:`ServiceError` is raised so the caller can surface it.
        """
        if capcut_api.requests is None:
            raise ServiceError("The 'requests' package is required. Run: pip install requests")
        config.validated()

        out: List[Optional[str]] = [None] * len(texts)  # None = not yet translated
        total = len(texts)
        for start in range(0, total, _BATCH_SIZE):
            batch = texts[start : start + _BATCH_SIZE]
            if logger:
                logger.info(
                    f"Translating lines {start + 1}-{start + len(batch)} of {total} ..."
                )
            self._translate_recursive(batch, start, out, config, _BATCH_SIZE, logger)

        # Any line still missing (model kept dropping it) falls back to source.
        missing = [i for i, v in enumerate(out) if v is None]
        if missing and logger:
            logger.warning(
                f"{len(missing)} line(s) could not be translated; keeping original text."
            )
        return [v if v is not None else texts[i] for i, v in enumerate(out)]

    # -- internals -------------------------------------------------------
    def _translate_recursive(
        self,
        batch: List[str],
        base: int,
        out: List[Optional[str]],
        config: TranslatorConfig,
        size: int,
        logger: Optional[Any],
    ) -> None:
        """Translate *batch* (whose first line is index *base* in *out*).

        Writes each translated line into ``out[base + offset]``. Lines the model
        drops or truncates are collected and re-translated in smaller sub-batches
        down to single lines, so a truncated reply never aborts the whole run.
        """
        translated = self._translate_batch(batch, config)  # dict: offset -> text
        for offset, value in translated.items():
            out[base + offset] = value

        missing = [i for i in range(len(batch)) if out[base + i] is None]
        if not missing:
            return

        # If we can't split further, give up on these lines (source is kept).
        if size <= _MIN_BATCH_SIZE and len(missing) == len(batch):
            return

        next_size = max(_MIN_BATCH_SIZE, min(size, len(batch)) // 2)
        if logger:
            logger.info(
                f"Retrying {len(missing)} untranslated line(s) in smaller batches ..."
            )
        # Re-translate the missing lines in contiguous runs at the smaller size.
        run: List[int] = []

        def flush() -> None:
            if not run:
                return
            sub = [batch[i] for i in run]
            for chunk_start in range(0, len(sub), next_size):
                chunk_idx = run[chunk_start : chunk_start + next_size]
                chunk = [batch[i] for i in chunk_idx]
                self._translate_recursive(
                    chunk, base + chunk_idx[0], out, config, next_size, logger
                )
            run.clear()

        prev = None
        for i in missing:
            if prev is not None and i != prev + 1:
                flush()
            run.append(i)
            prev = i
        flush()

    def _translate_batch(self, batch: List[str], config: TranslatorConfig) -> Dict[int, str]:
        """Return ``{offset: translation}`` for whatever the model returned.

        A truncated or partial reply yields only the offsets it managed to
        return; the caller detects the gaps and retries them. Raises only when
        the reply is unusable (empty / not locatable JSON / HTTP failure).
        """
        items = [{"id": i, "text": t} for i, t in enumerate(batch)]
        user_content = (
            f"Target language: {config.target_language}.\n"
            + (f"Style / tone instructions: {config.style_prompt}\n" if config.style_prompt.strip() else "")
            + "Translate the \"text\" of each item below.\n"
            + "Input JSON:\n"
            + json.dumps(items, ensure_ascii=False)
        )

        payload: Dict[str, Any] = {
            "model": config.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            # Ask for strict JSON; stripped automatically if the endpoint rejects it.
            "response_format": {"type": "json_object"},
            # Give the reply room so a full batch's JSON isn't truncated.
            "max_tokens": _MAX_TOKENS,
            "max_completion_tokens": _MAX_TOKENS,
        }
        if config.temperature is not None:
            payload["temperature"] = config.temperature
        headers = {"Content-Type": "application/json"}
        if config.api_key.strip():
            headers["Authorization"] = f"Bearer {config.api_key.strip()}"

        content = self._post(config.base_url.strip(), headers, payload)
        return self._parse_batch(content, batch)

    def _post(self, url: str, headers: Dict[str, str], payload: Dict[str, Any]) -> str:
        """POST the chat request, retrying once without optional fields on 400.

        Some endpoints/models reject ``response_format`` or an explicit
        ``temperature`` with an HTTP 400. Rather than fail, we progressively drop
        those optional fields and retry so a wider range of servers work.
        """
        attempt = dict(payload)
        last_error = ""
        optional = ("response_format", "max_completion_tokens", "max_tokens", "temperature")
        # Successively remove the fields most likely to be unsupported.
        for drop in (None, *optional):
            if drop is not None:
                if drop not in attempt:
                    continue
                attempt = {k: v for k, v in attempt.items() if k != drop}
            data = self._raw_post(url, headers, attempt)
            if data is not None:
                content = self._extract_content(data)
                if content is not None:
                    return content
                last_error = f"Unexpected AI response shape: {str(data)[:300]}"
                break
            last_error = self._last_http_error
            # Only keep retrying while there is still an optional field to drop.
            if not any(f in attempt for f in optional):
                break
        raise ServiceError(last_error or "AI request failed.")

    _last_http_error: str = ""

    def _raw_post(self, url: str, headers: Dict[str, str], payload: Dict[str, Any]):
        """Return parsed JSON on success, or ``None`` on an HTTP 400 (retryable)."""
        try:
            resp = capcut_api.requests.post(
                url, headers=headers, data=json.dumps(payload).encode("utf-8"), timeout=self.timeout
            )
        except Exception as exc:
            raise ServiceError(f"AI request failed: {exc}") from exc
        if resp.status_code == 400:
            self._last_http_error = f"AI endpoint returned HTTP 400: {resp.text[:300]}"
            return None  # retryable: an optional field may be unsupported
        if resp.status_code >= 400:
            raise ServiceError(f"AI endpoint returned HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            return resp.json()
        except ValueError as exc:
            raise ServiceError(f"AI endpoint returned non-JSON: {resp.text[:300]}") from exc

    @staticmethod
    def _extract_content(data: Any) -> Optional[str]:
        """Pull ``choices[0].message.content`` from an OpenAI-compatible reply."""
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            return None
        content = message.get("content") if isinstance(message, dict) else None
        # Some servers return content as a list of parts ({"type","text"}).
        if isinstance(content, list):
            parts = [p.get("text", "") for p in content if isinstance(p, dict)]
            content = "".join(parts)
        return content if isinstance(content, str) else None

    @staticmethod
    def _extract_json(content: str) -> Optional[Any]:
        """Pull a JSON object/array out of a possibly-noisy model reply.

        Reasoning models often emit a ``<thinking>...</thinking>`` block, prose,
        or ```` ```json ```` fences around the actual JSON. We progressively
        strip those, then fall back to scanning for the first balanced ``{...}``
        or ``[...]`` span (respecting strings/escapes) and parsing that.
        """
        if not content:
            return None
        text = content.strip()

        # Drop any <thinking>/<think>/<reasoning> block the model prepended.
        for tag in ("thinking", "think", "reasoning", "analysis"):
            close = f"</{tag}>"
            idx = text.rfind(close)
            if idx != -1:
                text = text[idx + len(close) :].strip()

        # Strip ```json ... ``` (or bare ```) fences anywhere in the text.
        if "```" in text:
            fence = text.find("```")
            rest = text[fence + 3 :]
            newline = rest.find("\n")
            if newline != -1:
                rest = rest[newline + 1 :]
            end = rest.rfind("```")
            if end != -1:
                rest = rest[:end]
            text = rest.strip()

        # Direct parse first.
        try:
            return json.loads(text)
        except ValueError:
            pass

        # Fall back to the first balanced JSON object/array in the text.
        span = Translator._first_json_span(text)
        if span is not None:
            try:
                return json.loads(span)
            except ValueError:
                return None
        return None

    @staticmethod
    def _first_json_span(text: str) -> Optional[str]:
        """Return the first balanced ``{...}`` or ``[...]`` substring, or None."""
        start = -1
        opener = closer = ""
        for i, ch in enumerate(text):
            if ch in "{[":
                start = i
                opener = ch
                closer = "}" if ch == "{" else "]"
                break
        if start == -1:
            return None

        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        return None

    @staticmethod
    def _parse_batch(content: str, batch: List[str]) -> Dict[int, str]:
        """Map the model's reply to ``{offset: translation}`` by id, order-safe.

        Returns only the offsets the model actually returned. A truncated reply
        (valid JSON that got cut off mid-array) still yields every complete item
        via a salvage pass, so partial progress is never lost. Raises only when
        nothing at all can be recovered.
        """
        items = Translator._extract_items(content)
        if items is None:
            raise ServiceError(f"Could not parse AI translation JSON: {content[:300]}")

        result: Dict[int, str] = {}
        for entry in items:
            if not isinstance(entry, dict):
                continue
            try:
                idx = int(entry.get("id"))
            except (TypeError, ValueError):
                continue
            text = entry.get("text")
            if 0 <= idx < len(batch) and text is not None:
                result[idx] = str(text)
        if not result:
            raise ServiceError(f"AI translation JSON contained no usable items: {content[:300]}")
        return result

    @staticmethod
    def _extract_items(content: str) -> Optional[List[Any]]:
        """Return the list of translation items, tolerating truncated replies."""
        parsed = Translator._extract_json(content)
        if isinstance(parsed, dict):
            items = parsed.get("items")
            if isinstance(items, list):
                return items
        elif isinstance(parsed, list):
            return parsed
        # The reply may be valid-but-truncated JSON (cut off mid-array). Salvage
        # every complete ``{...}`` object from it so partial work isn't wasted.
        return Translator._salvage_objects(content)

    @staticmethod
    def _salvage_objects(content: str) -> Optional[List[Any]]:
        """Extract every complete ``{...}`` object from noisy/truncated text.

        Used when the JSON envelope is truncated: we can't parse the whole
        document, but each finished ``{"id":..,"text":".."}`` object is intact
        and independently parseable. The item objects are nested inside the outer
        ``{"items":[...]}`` wrapper (which never closes when truncated), so we
        track ``{`` positions on a stack and parse every balanced ``{...}`` span
        at any depth, keeping those that look like translation items. Returns
        ``None`` if none are found.
        """
        objects: List[Any] = []
        stack: List[int] = []
        in_string = False
        escape = False
        for i, ch in enumerate(content):
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                stack.append(i)
            elif ch == "}":
                if stack:
                    start = stack.pop()
                    chunk = content[start : i + 1]
                    try:
                        obj = json.loads(chunk)
                    except ValueError:
                        continue
                    if isinstance(obj, dict) and "id" in obj:
                        objects.append(obj)
        return objects or None
