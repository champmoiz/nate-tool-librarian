def build_recommend_schema(tool_names: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "picks": {
                "type": "array",
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "tool": {"type": "string", "enum": tool_names},
                        "why": {"type": "string"},
                    },
                    "required": ["tool", "why"],
                },
            }
        },
        "required": ["picks"],
    }


def build_howto_schema(tool_names: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "picks": {
                "type": "array",
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "tool": {"type": "string", "enum": tool_names},
                        "why": {"type": "string"},
                    },
                    "required": ["tool", "why"],
                },
            },
            "flow": {
                "type": "array",
                "minItems": 3,
                "maxItems": 6,
                "items": {
                    "type": "object",
                    "properties": {
                        "stage": {"type": "string"},
                        "tool": {"type": "string", "enum": tool_names + ["none"]},
                    },
                    "required": ["stage", "tool"],
                },
            },
        },
        "required": ["picks", "flow"],
    }


def build_define_schema(resolved_name: str) -> dict:
    return {
        "type": "object",
        "properties": {
            "tool": {"type": "string", "enum": [resolved_name]},
            "definition": {"type": "string"},
        },
        "required": ["tool", "definition"],
    }


def build_factcheck_schema(resolved_name: str) -> dict:
    return {
        "type": "object",
        "properties": {
            "tool": {"type": "string", "enum": [resolved_name]},
            "verdict": {"type": "string", "enum": ["yes", "no", "partly", "unknown"]},
            "explanation": {"type": "string"},
        },
        "required": ["tool", "verdict", "explanation"],
    }


def build_schema(tool_names: list[str]) -> dict:
    return build_recommend_schema(tool_names)
