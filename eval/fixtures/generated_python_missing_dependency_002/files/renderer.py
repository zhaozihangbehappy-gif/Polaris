from widgetlib import parse_widget


def normalized_label(raw: str) -> str:
    parsed = parse_widget(raw)
    return parsed["name"].upper()
