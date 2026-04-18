import abc
import jinja2
from typing import Any
from pydantic import BaseModel
from pipeline.models.output import DiagramType


class DomainPlugin(abc.ABC):
    """Abstract base class for domain plugins."""

    domain_id: str

    @abc.abstractmethod
    def get_extraction_schema(self) -> type[BaseModel]:
        """Return the root Pydantic model for extraction in this domain."""
        pass

    @abc.abstractmethod
    def get_prompt(self, stage: str, version: int) -> str:
        """Return the raw Jinja2 template string for the given stage and version."""
        pass

    @abc.abstractmethod
    def get_diagram_types(self) -> list[DiagramType]:
        """Return the list of DiagramTypes supported by this domain."""
        pass

    @abc.abstractmethod
    def supports_codegen(self) -> bool:
        """Return True if this domain supports code generation."""
        pass

    def render_prompt(self, stage: str, version: int, **context: Any) -> str:
        """Loads and renders the Jinja2 template with the provided context."""
        template_str = self.get_prompt(stage, version)
        env = jinja2.Environment()
        template = env.from_string(template_str)
        return template.render(**context)
