from sat.providers.base import LLMProvider

class CopilotProvider(LLMProvider):
    def __init__(self, config):
        super().__init__(config)
        # No API key required for Copilot

    async def generate(
        self,
        system_prompt: str,
        messages: list,
        max_tokens: int = 16384,
        temperature: float = 0.3,
    ):
        # Placeholder: Implement Copilot LLM call here
        prompt = system_prompt
        from sat.providers.base import LLMResult, LLMUsage
        return LLMResult(text="Copilot response (mock)", usage=LLMUsage())

    async def generate_structured(
        self,
        system_prompt: str,
        messages: list,
        output_schema,
        max_tokens: int = 16384,
        temperature: float = 0.3,
    ):
        # Return a valid mock result for any schema
        # Fill required fields with dummy values
        # Assign mock values based on field type
        fields = {}
        for name, field in getattr(output_schema, "__fields__", {}).items():
            if hasattr(field, 'annotation'):
                typ = field.annotation
                if typ == list or str(typ).startswith('list'):
                    fields[name] = []
                elif typ == dict or str(typ).startswith('dict'):
                    fields[name] = {}
                else:
                    fields[name] = "mock"
            else:
                fields[name] = "mock"
        return output_schema(**fields)
