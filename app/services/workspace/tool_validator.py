"""Tool Input Validator — validates args before tool execution.

Loads schemas from knowledge/tools/*.yaml and validates args.
Lightweight — no heavy dependencies, just basic type/pattern checks.
"""
import re
from pathlib import Path
from typing import Optional
import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_TOOLS_DIR = _PROJECT_ROOT / "knowledge" / "tools"

# Cache loaded schemas
_cached_schemas: Optional[dict] = None


def _load_schemas() -> dict:
    """Load input schemas from knowledge/tools/*.yaml."""
    global _cached_schemas
    if _cached_schemas is not None:
        return _cached_schemas

    schemas = {}
    if not _TOOLS_DIR.exists():
        return schemas

    for f in _TOOLS_DIR.glob("*.yaml"):
        if f.name.startswith("_"):
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if data and data.get("id") and data.get("input_schema"):
                schemas[data["id"]] = data["input_schema"]
        except Exception:
            pass

    _cached_schemas = schemas
    return schemas


def validate_tool_args(tool_name: str, args: dict) -> tuple[bool, str]:
    """Validate tool arguments against schema.

    Returns: (is_valid, error_message)
    - (True, "") if valid
    - (False, "reason") if invalid
    """
    schemas = _load_schemas()
    schema = schemas.get(tool_name)

    if not schema:
        return True, ""  # No schema = no validation (backwards compat)

    # Check required fields
    for field_name, field_def in schema.items():
        if isinstance(field_def, dict):
            required = field_def.get("required", False)
            if required and field_name not in args:
                return False, f"Campo obrigatorio '{field_name}' nao fornecido"

            value = args.get(field_name)
            if value is not None:
                # Type check
                expected_type = field_def.get("type", "string")
                if expected_type == "string" and not isinstance(value, str):
                    args[field_name] = str(value)  # Auto-convert
                elif expected_type == "number" and not isinstance(value, (int, float)):
                    try:
                        args[field_name] = int(value)
                    except (ValueError, TypeError):
                        return False, f"Campo '{field_name}' deve ser numerico, recebeu '{value}'"

                # Pattern check (e.g. table code pattern)
                pattern = field_def.get("pattern")
                if pattern and isinstance(value, str):
                    if not re.match(pattern, value):
                        # Try uppercase
                        if re.match(pattern, value.upper()):
                            args[field_name] = value.upper()
                        # Don't fail — just warn
        elif isinstance(field_def, str):
            # Simple format: just description, no validation
            pass

    return True, ""


def fix_common_arg_issues(tool_name: str, args: dict) -> dict:
    """Auto-fix common argument issues.

    - Uppercase table codes (sb1 -> SB1)
    - Uppercase field codes (b1_cod -> B1_COD)
    - Convert string numbers to int for tamanho fields
    - Strip whitespace
    """
    fixed = dict(args)

    for key, value in fixed.items():
        if isinstance(value, str):
            value = value.strip()
            fixed[key] = value

            # Uppercase table codes
            if key in ("tabela",) and re.match(r'^[a-z][a-z0-9]{2}$', value, re.I):
                fixed[key] = value.upper()

            # Uppercase field codes
            if key in ("campo",) and re.match(r'^[a-z][a-z0-9]{1,2}_\w+$', value, re.I):
                fixed[key] = value.upper()

            # Uppercase arquivo names
            if key in ("arquivo",) and value and not value.endswith(('.prw', '.PRW', '.tlpp', '.TLPP')):
                # Add .prw if missing
                if '.' not in value:
                    fixed[key] = value + ".prw"

        # Convert string numbers
        if key in ("novo_tamanho", "contexto") and isinstance(value, str):
            try:
                fixed[key] = int(value)
            except ValueError:
                pass

    return fixed
