from typing import Any

from anthropic import AsyncAnthropic

from app.llm.provider import SchemaT

DEFAULT_MAX_TOKENS = 4096


class AnthropicProvider:
    """LLMProvider implementation backed by the Anthropic Messages API."""

    def __init__(self, api_key: str, model: str = "claude-opus-5") -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    def _build_request(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        max_tokens = kwargs.pop("max_tokens", DEFAULT_MAX_TOKENS)
        system = kwargs.pop("system", None)
        request: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system is not None:
            request["system"] = system
        request.update(kwargs)
        return request

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        response = await self._client.messages.create(**self._build_request(prompt, **kwargs))
        return "".join(block.text for block in response.content if block.type == "text")

    async def generate_structured(
        self, prompt: str, schema: type[SchemaT], **kwargs: Any
    ) -> SchemaT:
        request = self._build_request(prompt, **kwargs)
        response = await self._client.messages.parse(output_format=schema, **request)
        parsed = response.parsed_output
        if not isinstance(parsed, schema):
            raise TypeError(f"Expected {schema.__name__}, got {type(parsed).__name__}")
        return parsed
