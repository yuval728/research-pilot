from pathlib import Path
from pydantic import BaseModel

from pipeline.models.output import DiagramType
from pipeline.domains.base import DomainPlugin
from pipeline.domains.registry import registry
from pipeline.domains.ai_ml.schema import AiMlExtraction


class AiMlPlugin(DomainPlugin):
    """Domain Plugin implementation for AI/ML papers."""

    domain_id = "ai_ml"

    def get_extraction_schema(self) -> type[BaseModel]:
        return AiMlExtraction

    def get_prompt(self, stage: str, version: int) -> str:
        prompt_path = Path(__file__).parent / "prompts" / f"{stage}_v{version}.j2"
        if not prompt_path.exists():
            raise FileNotFoundError(
                f"Prompt template not found for stage {stage} v{version}: {prompt_path}"
            )
        return prompt_path.read_text(encoding="utf-8")

    def get_diagram_types(self) -> list[DiagramType]:
        # Return all three defined diagram types
        return [
            DiagramType.ARCHITECTURE,
            DiagramType.TRAINING_FLOW,
            DiagramType.INFERENCE_FLOW,
        ]

    def supports_codegen(self) -> bool:
        return True


# Auto-register the plugin when this module is imported by registry.auto_discover()
registry.register(AiMlPlugin())
