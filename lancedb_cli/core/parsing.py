"""Value/clause parsing helpers, used by command handlers."""

from typing import Any, Dict

MAX_FIELD_LENGTH = 50


def truncate_value(value: Any, max_len: int = MAX_FIELD_LENGTH) -> str:
    """Truncate long values and add ellipsis."""
    value_str = str(value)
    if len(value_str) > max_len:
        return value_str[:max_len] + "..."
    return value_str


def convert_value(value: str) -> Any:
    """Convert a string value to appropriate type."""
    if value.lower() == "true":
        return True
    elif value.lower() == "false":
        return False
    elif value.lower() in ("null", "none"):
        return None
    elif (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    else:
        try:
            if '.' not in value:
                return int(value)
            else:
                return float(value)
        except ValueError:
            return value


def parse_set_clause(set_clause: str) -> Dict[str, Any]:
    """Parse SET clause into key-value pairs with type conversion."""
    update_values = {}

    # Split on comma, but be careful about commas within quoted strings
    pairs = []
    current = ""
    in_quotes = False
    quote_char = None

    for char in set_clause:
        if char in ('"', "'") and (not in_quotes or char == quote_char):
            in_quotes = not in_quotes
            if in_quotes:
                quote_char = char
            else:
                quote_char = None
        if char == "," and not in_quotes:
            pairs.append(current)
            current = ""
        else:
            current += char
    if current:
        pairs.append(current)

    for pair in pairs:
        pair = pair.strip()
        if "=" not in pair:
            raise ValueError("Invalid SET clause format. Use key=value pairs separated by commas")

        key, value = pair.split("=", 1)
        key = key.strip()
        value = value.strip()
        update_values[key] = convert_value(value)

    return update_values
