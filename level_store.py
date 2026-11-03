import json
import os
from pathlib import Path

from settings import (
    BRICK_COLS,
    CUSTOM_LEVELS_FILE,
    EDITOR_ROWS,
    LEVEL_CHARS,
    MAX_LEVEL_NAME,
)

DESTRUCTIBLE_CHARS = "NABP"


def default_path():
    return Path(__file__).with_name(CUSTOM_LEVELS_FILE)


def normalize_level(level):
    if not isinstance(level, dict):
        return None
    raw_name = level.get("name", "")
    name = str(raw_name).strip()[:MAX_LEVEL_NAME]
    if not name:
        name = "Custom Level"
    raw_rows = level.get("rows", [])
    if not isinstance(raw_rows, list):
        return None
    rows = []
    for row_index in range(EDITOR_ROWS):
        source = raw_rows[row_index] if row_index < len(raw_rows) else ""
        if not isinstance(source, str):
            source = ""
        cells = []
        for column_index in range(BRICK_COLS):
            char = source[column_index] if column_index < len(source) else "."
            cells.append(char if char in LEVEL_CHARS else ".")
        rows.append("".join(cells))
    if not any(char in DESTRUCTIBLE_CHARS for row in rows for char in row):
        return None
    return {"name": name, "rows": rows}


def load_custom_levels(path=None):
    file_path = Path(path) if path is not None else default_path()
    if not file_path.exists():
        return []
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    raw_levels = data.get("levels", []) if isinstance(data, dict) else data
    if not isinstance(raw_levels, list):
        return []
    levels = []
    for raw_level in raw_levels:
        normalized = normalize_level(raw_level)
        if normalized is not None:
            levels.append(normalized)
    return levels


def save_custom_levels(levels, path=None):
    file_path = Path(path) if path is not None else default_path()
    normalized = []
    for level in levels:
        cleaned = normalize_level(level)
        if cleaned is not None:
            normalized.append(cleaned)
    payload = {"version": 1, "levels": normalized}
    temporary = file_path.with_name(file_path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temporary, file_path)
        return True
    except OSError:
        try:
            if temporary.exists():
                temporary.unlink()
        except OSError:
            pass
        return False
