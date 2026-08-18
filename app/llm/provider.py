from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LLMProvider(Protocol):
    """Provider-agnostic abstraction over a chat-completion LLM.

    Implementations must not be assumed to be Anthropic-specific anywhere
    else in the codebase -- callers depend only on this Protocol.
    """

    async def generate(self, prompt: str, **kwargs: Any) -> str: ...

    async def generate_structured(
        self, prompt: str, schema: type[SchemaT], **kwargs: Any
    ) -> SchemaT: ...
