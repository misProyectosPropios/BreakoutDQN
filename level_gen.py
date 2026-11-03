import random
from collections import deque

from level_store import load_custom_levels
from levels import LEVELS
from settings import EDITOR_COLS, EDITOR_ROWS

DESTRUCTIBLE = "NABP"
BRICK_TYPES = ["N", "A", "B", "P"]
BRICK_WEIGHTS = [62, 16, 11, 11]
ARCHETYPES = ["rows", "pyramid", "diamond", "checker", "columns", "random", "fortress"]


def _normalized_rows(level):
    source = level.get("rows", []) if isinstance(level, dict) else level
    if not isinstance(source, (list, tuple)):
        source = []
    rows = []
    for row_index in range(EDITOR_ROWS):
        raw = source[row_index] if row_index < len(source) else ""
        if not isinstance(raw, str):
            raw = ""
        cells = []
        for column_index in range(EDITOR_COLS):
            char = raw[column_index] if column_index < len(raw) else "."
            cells.append(char if char in ".NABPX" else ".")
        rows.append("".join(cells))
    return rows


def is_solvable(level):
    rows = _normalized_rows(level)
    if not any(char in DESTRUCTIBLE for row in rows for char in row):
        return False
    visited = set()
    queue = deque()
    for row_index in range(EDITOR_ROWS):
        for column_index in range(EDITOR_COLS):
            on_open_edge = (
                row_index == EDITOR_ROWS - 1
                or column_index == 0
                or column_index == EDITOR_COLS - 1
            )
            if on_open_edge and rows[row_index][column_index] != "X":
                visited.add((row_index, column_index))
                queue.append((row_index, column_index))
    while queue:
        row_index, column_index = queue.popleft()
        for delta_row, delta_column in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            next_row = row_index + delta_row
            next_column = column_index + delta_column
            if not (0 <= next_row < EDITOR_ROWS and 0 <= next_column < EDITOR_COLS):
                continue
            if (next_row, next_column) in visited:
                continue
            if rows[next_row][next_column] == "X":
                continue
            visited.add((next_row, next_column))
            queue.append((next_row, next_column))
    for row_index in range(EDITOR_ROWS):
        for column_index in range(EDITOR_COLS):
            if rows[row_index][column_index] not in DESTRUCTIBLE:
                continue
            if (row_index, column_index) in visited:
                continue
            neighbours = (
                (row_index - 1, column_index),
                (row_index + 1, column_index),
                (row_index, column_index - 1),
                (row_index, column_index + 1),
            )
            if not any(neighbour in visited for neighbour in neighbours):
                return False
    return True


def _blank_rows():
    return ["." * EDITOR_COLS for _ in range(EDITOR_ROWS)]


def _put(rows, row, column, char):
    if 0 <= row < EDITOR_ROWS and 0 <= column < EDITOR_COLS:
        rows[row] = rows[row][:column] + char + rows[row][column + 1 :]


def _random_type(rng):
    return rng.choices(BRICK_TYPES, weights=BRICK_WEIGHTS, k=1)[0]


def _fill_row(rows, row, rng, probability=0.8):
    for column in range(EDITOR_COLS):
        if rng.random() < probability:
            _put(rows, row, column, _random_type(rng))


def _gen_rows(rows, rng):
    top = rng.randint(0, 3)
    height = rng.randint(3, 7)
    for row in range(top, min(EDITOR_ROWS, top + height)):
        mode = rng.random()
        if mode < 0.3:
            _fill_row(rows, row, rng, 1.0)
        elif mode < 0.65:
            left = rng.randint(0, 3)
            right = rng.randint(EDITOR_COLS - 4, EDITOR_COLS - 1)
            for column in range(left, right + 1):
                if rng.random() < 0.8:
                    _put(rows, row, column, _random_type(rng))
        else:
            for column in range(EDITOR_COLS):
                if rng.random() < 0.45:
                    _put(rows, row, column, _random_type(rng))


def _gen_pyramid(rows, rng):
    top = rng.randint(0, 2)
    height = rng.randint(3, 5)
    center = EDITOR_COLS // 2
    for offset in range(height):
        row = top + offset
        left = max(0, center - offset)
        right = min(EDITOR_COLS - 1, center + offset)
        for column in range(left, right + 1):
            if rng.random() < 0.9:
                _put(rows, row, column, _random_type(rng))


def _gen_diamond(rows, rng):
    top = rng.randint(0, 2)
    height = rng.randint(3, 5)
    center = EDITOR_COLS // 2
    for offset in range(height):
        row = top + offset
        half = min(offset, height - 1 - offset)
        left = max(0, center - half)
        right = min(EDITOR_COLS - 1, center + half)
        for column in range(left, right + 1):
            if rng.random() < 0.9:
                _put(rows, row, column, _random_type(rng))


def _gen_checker(rows, rng):
    top = rng.randint(0, 2)
    height = rng.randint(4, 8)
    phase = rng.randint(0, 1)
    for row in range(top, min(EDITOR_ROWS, top + height)):
        for column in range(EDITOR_COLS):
            if (row + column + phase) % 2 == 0 and rng.random() < 0.8:
                _put(rows, row, column, _random_type(rng))


def _gen_columns(rows, rng):
    columns = rng.sample(range(EDITOR_COLS), rng.randint(3, 7))
    for column in columns:
        top = rng.randint(0, 3)
        length = rng.randint(2, min(7, EDITOR_ROWS - top))
        for row in range(top, top + length):
            if rng.random() < 0.8:
                _put(rows, row, column, _random_type(rng))


def _gen_random(rows, rng):
    top = rng.randint(0, 4)
    bottom = rng.randint(top + 3, min(EDITOR_ROWS - 1, top + 8))
    density = rng.uniform(0.15, 0.5)
    for row in range(top, bottom + 1):
        for column in range(EDITOR_COLS):
            if rng.random() < density:
                _put(rows, row, column, _random_type(rng))


def _gen_fortress(rows, rng):
    _gen_rows(rows, rng)
    for _ in range(rng.randint(2, 5)):
        column = rng.randrange(EDITOR_COLS)
        top = rng.randint(0, 5)
        length = rng.randint(1, 4)
        for row in range(top, min(EDITOR_ROWS, top + length)):
            if rows[row][column] == "." and rng.random() < 0.7:
                _put(rows, row, column, "X")


BUILDERS = {
    "rows": _gen_rows,
    "pyramid": _gen_pyramid,
    "diamond": _gen_diamond,
    "checker": _gen_checker,
    "columns": _gen_columns,
    "random": _gen_random,
    "fortress": _gen_fortress,
}


def _add_walls(rows, rng):
    for _ in range(rng.randint(1, 5)):
        column = rng.randrange(EDITOR_COLS)
        top = rng.randint(0, 6)
        length = rng.randint(1, 3)
        for row in range(top, min(EDITOR_ROWS, top + length)):
            if rows[row][column] == "." and rng.random() < 0.75:
                _put(rows, row, column, "X")


def generate_random_level(rng):
    for _ in range(80):
        archetype = rng.choice(ARCHETYPES)
        rows = _blank_rows()
        BUILDERS[archetype](rows, rng)
        if archetype != "fortress" and rng.random() < 0.3:
            _add_walls(rows, rng)
        level = {"name": f"Random {archetype.title()}", "rows": rows, "source": "procedural"}
        destructible = sum(1 for row in rows for char in row if char in DESTRUCTIBLE)
        walls = sum(1 for row in rows for char in row if char == "X")
        if not (8 <= destructible <= 60):
            continue
        if walls > 14:
            continue
        if is_solvable(level):
            return level

    rows = _blank_rows()
    top = rng.randint(1, 3)
    for row in range(top, top + rng.randint(3, 6)):
        for column in range(EDITOR_COLS):
            if rng.random() < 0.7:
                _put(rows, row, column, _random_type(rng))
    return {"name": "Random Fallback", "rows": rows, "source": "procedural"}


def _tag_level(level, source):
    return {
        "name": level.get("name", "Level"),
        "rows": _normalized_rows(level),
        "source": source,
    }


def build_static_levels(include_builtin=True, include_custom=True, custom_path=None):
    levels = []
    skipped = []
    if include_builtin:
        for level in LEVELS:
            tagged = _tag_level(level, "builtin")
            if is_solvable(tagged):
                levels.append(tagged)
            else:
                skipped.append(tagged["name"])
    if include_custom:
        for level in load_custom_levels(custom_path):
            tagged = _tag_level(level, "custom")
            if is_solvable(tagged):
                levels.append(tagged)
            else:
                skipped.append(tagged["name"])
    return levels, skipped


class LevelPool:
    def __init__(self, static_levels, procedural_ratio=0.5, rng=None):
        self.static_levels = list(static_levels)
        self.procedural_ratio = max(0.0, min(1.0, procedural_ratio))
        self.rng = rng if rng is not None else random.Random()

    def sample(self):
        if not self.static_levels:
            return generate_random_level(self.rng)
        if self.rng.random() < self.procedural_ratio:
            return generate_random_level(self.rng)
        return self.rng.choice(self.static_levels)
