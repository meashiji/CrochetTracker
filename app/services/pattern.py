def parse_pattern(text: str) -> list[tuple[int, str]]:
    lines = [line.strip() for line in text.splitlines()]
    non_blank = [line for line in lines if line]
    return [(i + 1, content) for i, content in enumerate(non_blank)]
