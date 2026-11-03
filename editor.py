import pygame

from level_store import load_custom_levels, save_custom_levels
from settings import (
    ACCENT,
    BRICK_COLORS,
    BRICK_GAP,
    BRICK_HEIGHT,
    BRICK_RADIUS,
    BRICK_TOP,
    BRICK_WIDTH,
    DIM_COLOR,
    EDITOR_COLS,
    EDITOR_ROWS,
    HEIGHT,
    HUD_COLOR,
    LEVEL_CHARS,
    MAX_LEVEL_NAME,
    WIDTH,
)

GRID_X = (WIDTH - (EDITOR_COLS * BRICK_WIDTH + (EDITOR_COLS - 1) * BRICK_GAP)) // 2
GRID_Y = BRICK_TOP
GRID_W = EDITOR_COLS * BRICK_WIDTH + (EDITOR_COLS - 1) * BRICK_GAP
GRID_H = EDITOR_ROWS * BRICK_HEIGHT + (EDITOR_ROWS - 1) * BRICK_GAP

PALETTE = [
    ("0", ".", "Erase", (58, 63, 82)),
    ("1", "N", "Normal", BRICK_COLORS["N"]),
    ("2", "A", "Armored", BRICK_COLORS["A"]),
    ("3", "B", "Bomb", BRICK_COLORS["B"]),
    ("4", "P", "Power-up", BRICK_COLORS["P"]),
    ("5", "X", "Wall", BRICK_COLORS["X"]),
]
PALETTE_KINDS = [entry[1] for entry in PALETTE]
DESTRUCTIBLE = "NABP"


def draw_level_preview(surface, rows, area):
    if not rows:
        return
    columns = max(len(row) for row in rows)
    row_count = len(rows)
    gap = 3
    max_width = area.width - 24
    max_height = area.height - 24
    cell_w = max(6, min(38, (max_width - (columns - 1) * gap) // max(1, columns)))
    cell_h = max(6, min(16, (max_height - (row_count - 1) * gap) // max(1, row_count)))
    grid_w = columns * cell_w + (columns - 1) * gap
    grid_h = row_count * cell_h + (row_count - 1) * gap
    start_x = area.centerx - grid_w // 2
    start_y = area.centery - grid_h // 2
    for row_index, row in enumerate(rows):
        for column_index, char in enumerate(row):
            x = start_x + column_index * (cell_w + gap)
            y = start_y + row_index * (cell_h + gap)
            rect = pygame.Rect(x, y, cell_w, cell_h)
            if char in BRICK_COLORS:
                color = BRICK_COLORS[char]
                pygame.draw.rect(surface, color, rect, border_radius=2)
                edge = tuple(min(255, channel + 55) for channel in color)
                pygame.draw.rect(surface, edge, rect, width=1, border_radius=2)
            else:
                pygame.draw.rect(surface, (28, 32, 52), rect, border_radius=2)


class LevelEditor:
    def __init__(self, background, path=None):
        self.background = background
        self.path = path
        self.font_tiny = pygame.font.Font(None, 20)
        self.font_small = pygame.font.Font(None, 26)
        self.font_medium = pygame.font.Font(None, 40)
        self.font_large = pygame.font.Font(None, 58)
        self.rows = ["." * EDITOR_COLS for _ in range(EDITOR_ROWS)]
        self.name = "Custom Level"
        self.loaded_index = None
        self.selected = "N"
        self.mode = "edit"
        self.pending = None
        self.name_buffer = ""
        self.name_error = ""
        self.load_index = 0
        self.load_offset = 0
        self.dirty = False
        self.message = ""
        self.message_timer = 0.0
        self.undo_stack = []
        self.painting = None
        self.last_cell = None
        self.levels = load_custom_levels(self.path)
        self.palette_rects = self._build_palette_rects()

    def _build_palette_rects(self):
        total_gap = 8 * (len(PALETTE) - 1)
        button_w = (GRID_W - total_gap) // len(PALETTE)
        button_h = 36
        y = GRID_Y + GRID_H + 18
        rects = []
        for index, (key, kind, label, color) in enumerate(PALETTE):
            x = GRID_X + index * (button_w + 8)
            rects.append((key, kind, label, color, pygame.Rect(x, y, button_w, button_h)))
        return rects

    def new_level(self):
        self.levels = load_custom_levels(self.path)
        self.rows = ["." * EDITOR_COLS for _ in range(EDITOR_ROWS)]
        self.name = self._next_default_name()
        self.loaded_index = None
        self.selected = "N"
        self.dirty = False
        self.undo_stack = []
        self.mode = "edit"
        self.pending = None
        self.painting = None
        self.last_cell = None
        self._set_message("New level")

    def load_level(self, level, index=None):
        self.levels = load_custom_levels(self.path)
        rows = list(level.get("rows", []))
        cleaned = []
        for row_index in range(EDITOR_ROWS):
            source = rows[row_index] if row_index < len(rows) else ""
            cells = []
            for column_index in range(EDITOR_COLS):
                char = source[column_index] if column_index < len(source) else "."
                cells.append(char if char in LEVEL_CHARS else ".")
            cleaned.append("".join(cells))
        self.rows = cleaned
        self.name = level.get("name", "Custom Level")
        if index is None:
            index = next((i for i, item in enumerate(self.levels) if item["name"] == self.name), None)
        self.loaded_index = index
        self.dirty = False
        self.undo_stack = []
        self.mode = "edit"
        self.pending = None
        self.painting = None
        self.last_cell = None
        self._set_message("Level loaded")

    def _next_default_name(self):
        existing = {level["name"] for level in self.levels}
        index = 1
        while f"Custom Level {index}" in existing:
            index += 1
        return f"Custom Level {index}"

    def _set_message(self, text):
        self.message = text
        self.message_timer = 2.5

    def update(self, dt):
        if self.message_timer > 0:
            self.message_timer = max(0.0, self.message_timer - dt)

    def handle_event(self, event):
        if self.mode == "name":
            return self._handle_name_event(event)
        if self.mode == "load":
            return self._handle_load_event(event)
        if self.mode == "confirm":
            return self._handle_confirm_event(event)
        if event.type == pygame.KEYDOWN:
            return self._handle_edit_key(event)
        if event.type == pygame.MOUSEBUTTONDOWN:
            return self._handle_mouse_down(event)
        if event.type == pygame.MOUSEMOTION:
            self._handle_mouse_motion(event)
        elif event.type == pygame.MOUSEBUTTONUP:
            self.painting = None
            self.last_cell = None
        return None

    def _handle_edit_key(self, event):
        key = event.key
        if key == pygame.K_ESCAPE:
            if self.dirty:
                self.mode = "confirm"
                self.pending = "exit"
                return None
            return "exit"
        if key == pygame.K_s:
            self._start_name_mode()
        elif key == pygame.K_n:
            if self.dirty:
                self.mode = "confirm"
                self.pending = "new"
            else:
                self.new_level()
        elif key == pygame.K_l:
            if self.dirty:
                self.mode = "confirm"
                self.pending = "load"
            else:
                self._open_load()
        elif key == pygame.K_z and event.mod & pygame.KMOD_CTRL:
            self._undo()
        elif pygame.K_0 <= key <= pygame.K_5:
            self.selected = PALETTE_KINDS[key - pygame.K_0]
        return None

    def _handle_mouse_down(self, event):
        for key, kind, label, color, rect in self.palette_rects:
            if rect.collidepoint(event.pos):
                self.selected = kind
                return None
        cell = self._cell_at(event.pos)
        if cell is None:
            return None
        if event.button == 1:
            self.painting = "paint"
            self._begin_stroke()
            self._apply_cell(cell[0], cell[1], self.selected)
            self.last_cell = cell
        elif event.button == 3:
            self.painting = "erase"
            self._begin_stroke()
            self._apply_cell(cell[0], cell[1], ".")
            self.last_cell = cell
        return None

    def _handle_mouse_motion(self, event):
        if not self.painting:
            return
        cell = self._cell_at(event.pos)
        if cell is None or cell == self.last_cell:
            return
        self.last_cell = cell
        kind = self.selected if self.painting == "paint" else "."
        self._apply_cell(cell[0], cell[1], kind)

    def _cell_at(self, pos):
        x, y = pos
        if x < GRID_X or y < GRID_Y or x >= GRID_X + GRID_W or y >= GRID_Y + GRID_H:
            return None
        column = (x - GRID_X) // (BRICK_WIDTH + BRICK_GAP)
        row = (y - GRID_Y) // (BRICK_HEIGHT + BRICK_GAP)
        if not (0 <= column < EDITOR_COLS and 0 <= row < EDITOR_ROWS):
            return None
        cell_x = GRID_X + column * (BRICK_WIDTH + BRICK_GAP)
        cell_y = GRID_Y + row * (BRICK_HEIGHT + BRICK_GAP)
        if x >= cell_x + BRICK_WIDTH or y >= cell_y + BRICK_HEIGHT:
            return None
        return row, column

    def _begin_stroke(self):
        self.undo_stack.append(list(self.rows))
        if len(self.undo_stack) > 60:
            self.undo_stack.pop(0)

    def _apply_cell(self, row, column, kind):
        char = "." if kind == "." else kind
        if char not in LEVEL_CHARS:
            char = "."
        current = self.rows[row]
        if current[column] == char:
            return
        self.rows[row] = current[:column] + char + current[column + 1 :]
        self.dirty = True

    def _undo(self):
        if not self.undo_stack:
            self._set_message("Nothing to undo")
            return
        self.rows = self.undo_stack.pop()
        self.dirty = True
        self._set_message("Undo")

    def _start_name_mode(self):
        self.mode = "name"
        self.name_buffer = self.name
        self.name_error = ""

    def _handle_name_event(self, event):
        if event.type != pygame.KEYDOWN:
            return None
        if event.key == pygame.K_ESCAPE:
            self.mode = "edit"
            self.name_error = ""
            return None
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._save()
            return None
        if event.key == pygame.K_BACKSPACE:
            self.name_buffer = self.name_buffer[:-1]
            return None
        char = event.unicode
        if char and 32 <= ord(char) < 127 and len(self.name_buffer) < MAX_LEVEL_NAME:
            self.name_buffer += char
        return None

    def _save(self):
        name = self.name_buffer.strip()[:MAX_LEVEL_NAME]
        if not name:
            self.name_error = "Name cannot be empty"
            return
        if not any(char in DESTRUCTIBLE for row in self.rows for char in row):
            self.name_error = "Add at least one destructible brick"
            return
        level = {"name": name, "rows": list(self.rows)}
        if self.loaded_index is not None and 0 <= self.loaded_index < len(self.levels):
            self.levels[self.loaded_index] = level
        else:
            existing = next((i for i, item in enumerate(self.levels) if item["name"] == name), None)
            if existing is not None:
                self.levels[existing] = level
                self.loaded_index = existing
            else:
                self.levels.append(level)
                self.loaded_index = len(self.levels) - 1
        if save_custom_levels(self.levels, self.path):
            self.name = name
            self.dirty = False
            self.name_error = ""
            self.mode = "edit"
            self._set_message("Level saved")
        else:
            self.name_error = "Could not save file"

    def _open_load(self):
        self.levels = load_custom_levels(self.path)
        if not self.levels:
            self.mode = "edit"
            self._set_message("No saved levels yet")
            return
        self.mode = "load"
        self.load_index = self.loaded_index if self.loaded_index is not None else 0
        self.load_index = max(0, min(len(self.levels) - 1, self.load_index))

    def _handle_load_event(self, event):
        if event.type != pygame.KEYDOWN:
            return None
        if event.key == pygame.K_ESCAPE:
            self.mode = "edit"
        elif event.key in (pygame.K_UP, pygame.K_w):
            self.load_index = (self.load_index - 1) % len(self.levels)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.load_index = (self.load_index + 1) % len(self.levels)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            level = self.levels[self.load_index]
            self.load_level(level, self.load_index)
        return None

    def _handle_confirm_event(self, event):
        if event.type != pygame.KEYDOWN:
            return None
        if event.key in (pygame.K_y, pygame.K_RETURN, pygame.K_KP_ENTER):
            action = self.pending
            self.pending = None
            if action == "exit":
                return "exit"
            if action == "new":
                self.new_level()
            elif action == "load":
                self._open_load()
        elif event.key in (pygame.K_n, pygame.K_ESCAPE):
            self.pending = None
            self.mode = "edit"
        return None

    def draw(self, surface):
        surface.blit(self.background, (0, 0))
        self._draw_top(surface)
        self._draw_grid(surface)
        self._draw_palette(surface)
        self._draw_help(surface)
        if self.mode == "name":
            self._draw_name_dialog(surface)
        elif self.mode == "load":
            self._draw_load_dialog(surface)
        elif self.mode == "confirm":
            self._draw_confirm_dialog(surface)

    def _draw_top(self, surface):
        pygame.draw.line(surface, (52, 58, 94), (0, 45), (WIDTH, 45), 1)
        self._text(surface, "LEVEL EDITOR", self.font_small, ACCENT, topleft=(20, 12))
        suffix = " *" if self.dirty else ""
        self._text(surface, f"{self.name}{suffix}", self.font_small, HUD_COLOR, center=(WIDTH // 2, 24))
        self._text(surface, "MOUSE PAINT", self.font_tiny, DIM_COLOR, topleft=(WIDTH - 130, 17))

    def _draw_grid(self, surface):
        for row_index in range(EDITOR_ROWS):
            for column_index in range(EDITOR_COLS):
                x = GRID_X + column_index * (BRICK_WIDTH + BRICK_GAP)
                y = GRID_Y + row_index * (BRICK_HEIGHT + BRICK_GAP)
                rect = pygame.Rect(x, y, BRICK_WIDTH, BRICK_HEIGHT)
                char = self.rows[row_index][column_index]
                if char == ".":
                    pygame.draw.rect(surface, (24, 28, 48), rect, border_radius=4)
                    pygame.draw.rect(surface, (38, 43, 68), rect, width=1, border_radius=4)
                else:
                    self._draw_brick_cell(surface, rect, char)
        if self.mode == "edit":
            cell = self._cell_at(pygame.mouse.get_pos())
            if cell is not None:
                row_index, column_index = cell
                x = GRID_X + column_index * (BRICK_WIDTH + BRICK_GAP)
                y = GRID_Y + row_index * (BRICK_HEIGHT + BRICK_GAP)
                pygame.draw.rect(surface, ACCENT, (x - 1, y - 1, BRICK_WIDTH + 2, BRICK_HEIGHT + 2), width=2, border_radius=5)

    def _draw_brick_cell(self, surface, rect, char):
        color = BRICK_COLORS[char]
        pygame.draw.rect(surface, (5, 6, 14), rect.move(2, 3), border_radius=BRICK_RADIUS)
        pygame.draw.rect(surface, color, rect, border_radius=BRICK_RADIUS)
        edge = tuple(min(255, channel + 60) for channel in color)
        pygame.draw.rect(surface, edge, rect, width=2, border_radius=BRICK_RADIUS)
        inner = rect.inflate(-12, -12)
        if char == "B":
            pygame.draw.circle(surface, (255, 226, 150), inner.center, max(3, inner.height // 2))
            pygame.draw.circle(surface, (120, 30, 20), inner.center, max(1, inner.height // 5))
        elif char == "P":
            label = self.font_small.render("?", True, (8, 40, 24))
            surface.blit(label, label.get_rect(center=rect.center))
        elif char == "X":
            pygame.draw.rect(surface, (178, 186, 202), inner, width=1, border_radius=3)
            for point in (
                (inner.left + 3, inner.top + 3),
                (inner.right - 3, inner.top + 3),
                (inner.left + 3, inner.bottom - 3),
                (inner.right - 3, inner.bottom - 3),
            ):
                pygame.draw.circle(surface, (196, 204, 218), point, 1)
        elif char == "A":
            pygame.draw.rect(surface, (225, 205, 255), inner, width=1, border_radius=3)
        else:
            pygame.draw.rect(surface, (230, 240, 255), inner, width=1, border_radius=3)

    def _draw_palette(self, surface):
        for key, kind, label, color, rect in self.palette_rects:
            selected = kind == self.selected
            if selected:
                pygame.draw.rect(surface, ACCENT, rect.inflate(4, 4), border_radius=8)
            pygame.draw.rect(surface, (26, 30, 50), rect, border_radius=6)
            swatch = pygame.Rect(rect.left + 8, rect.top + 9, 18, 18)
            pygame.draw.rect(surface, color, swatch, border_radius=3)
            pygame.draw.rect(surface, (220, 226, 240), swatch, width=1, border_radius=3)
            text_color = (18, 20, 32) if selected else HUD_COLOR
            self._text(surface, f"{key} {label}", self.font_tiny, text_color, topleft=(rect.left + 32, rect.top + 11))

    def _draw_help(self, surface):
        self._text(
            surface,
            "LMB paint    RMB erase    drag to draw    0-5 select type",
            self.font_tiny,
            DIM_COLOR,
            center=(WIDTH // 2, GRID_Y + GRID_H + 72),
        )
        self._text(
            surface,
            "S save    L load    N new    CTRL+Z undo    ESC back",
            self.font_tiny,
            DIM_COLOR,
            center=(WIDTH // 2, GRID_Y + GRID_H + 94),
        )
        if self.message_timer > 0:
            self._text(surface, self.message, self.font_small, ACCENT, center=(WIDTH // 2, HEIGHT - 22))

    def _draw_shade(self, surface, alpha=190):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((4, 6, 16, alpha))
        surface.blit(overlay, (0, 0))

    def _draw_name_dialog(self, surface):
        self._draw_shade(surface)
        panel = pygame.Rect(0, 0, 520, 220)
        panel.center = (WIDTH // 2, HEIGHT // 2)
        pygame.draw.rect(surface, (18, 22, 40), panel, border_radius=12)
        pygame.draw.rect(surface, (60, 68, 104), panel, width=2, border_radius=12)
        self._text(surface, "LEVEL NAME", self.font_medium, ACCENT, center=(panel.centerx, panel.top + 40))
        field = pygame.Rect(panel.left + 40, panel.top + 78, panel.width - 80, 40)
        pygame.draw.rect(surface, (10, 12, 24), field, border_radius=6)
        pygame.draw.rect(surface, (70, 80, 120), field, width=1, border_radius=6)
        text_surface = self.font_small.render(self.name_buffer, True, HUD_COLOR)
        surface.blit(text_surface, (field.left + 10, field.centery - text_surface.get_height() // 2))
        if (pygame.time.get_ticks() // 400) % 2 == 0:
            cursor_x = field.left + 12 + text_surface.get_width()
            pygame.draw.line(surface, ACCENT, (cursor_x, field.top + 8), (cursor_x, field.bottom - 8), 2)
        if self.name_error:
            self._text(surface, self.name_error, self.font_tiny, (255, 120, 110), center=(panel.centerx, panel.top + 138))
        self._text(surface, "ENTER save    ESC cancel", self.font_tiny, DIM_COLOR, center=(panel.centerx, panel.bottom - 30))

    def _draw_load_dialog(self, surface):
        self._draw_shade(surface)
        panel = pygame.Rect(0, 0, 640, 420)
        panel.center = (WIDTH // 2, HEIGHT // 2)
        pygame.draw.rect(surface, (18, 22, 40), panel, border_radius=12)
        pygame.draw.rect(surface, (60, 68, 104), panel, width=2, border_radius=12)
        self._text(surface, "LOAD LEVEL", self.font_medium, ACCENT, center=(panel.centerx, panel.top + 34))
        list_area = pygame.Rect(panel.left + 24, panel.top + 68, 260, 280)
        preview_area = pygame.Rect(panel.left + 300, panel.top + 68, 316, 280)
        pygame.draw.rect(surface, (12, 15, 28), list_area, border_radius=8)
        pygame.draw.rect(surface, (12, 15, 28), preview_area, border_radius=8)
        visible = 9
        if self.load_index < self.load_offset:
            self.load_offset = self.load_index
        elif self.load_index >= self.load_offset + visible:
            self.load_offset = self.load_index - visible + 1
        start = max(0, min(self.load_offset, max(0, len(self.levels) - visible)))
        for slot in range(visible):
            index = start + slot
            if index >= len(self.levels):
                break
            row = pygame.Rect(list_area.left + 8, list_area.top + 8 + slot * 30, list_area.width - 16, 26)
            if index == self.load_index:
                pygame.draw.rect(surface, ACCENT, row, border_radius=5)
                color = (18, 20, 32)
            else:
                color = HUD_COLOR
            self._text(surface, self.levels[index]["name"], self.font_tiny, color, topleft=(row.left + 8, row.top + 6))
        if self.levels:
            preview = self.levels[self.load_index]
            draw_level_preview(surface, preview["rows"], preview_area.inflate(-16, -16))
            self._text(surface, preview["name"], self.font_tiny, DIM_COLOR, center=(preview_area.centerx, preview_area.bottom - 12))
        self._text(surface, "UP/DOWN select    ENTER load    ESC cancel", self.font_tiny, DIM_COLOR, center=(panel.centerx, panel.bottom - 26))

    def _draw_confirm_dialog(self, surface):
        self._draw_shade(surface)
        panel = pygame.Rect(0, 0, 480, 190)
        panel.center = (WIDTH // 2, HEIGHT // 2)
        pygame.draw.rect(surface, (18, 22, 40), panel, border_radius=12)
        pygame.draw.rect(surface, (60, 68, 104), panel, width=2, border_radius=12)
        self._text(surface, "UNSAVED CHANGES", self.font_medium, ACCENT, center=(panel.centerx, panel.top + 42))
        self._text(surface, "Discard the changes?", self.font_small, HUD_COLOR, center=(panel.centerx, panel.top + 92))
        self._text(
            surface,
            "Y / ENTER discard    N / ESC cancel",
            self.font_tiny,
            DIM_COLOR,
            center=(panel.centerx, panel.bottom - 32),
        )

    def _text(self, surface, text, font, color, center=None, topleft=None):
        image = font.render(text, True, color)
        rect = image.get_rect()
        if center is not None:
            rect.center = center
        elif topleft is not None:
            rect.topleft = topleft
        surface.blit(image, rect)
        return rect
