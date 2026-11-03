import math
import random

import pygame

from editor import LevelEditor, draw_level_preview
from entities import (
    Ball,
    Brick,
    Paddle,
    Particle,
    PowerUp,
    clamp_ball_direction,
    resolve_circle_rect,
)
from level_store import load_custom_levels, save_custom_levels
from levels import LEVELS
from settings import (
    ACCENT,
    BALL_COLOR,
    BALL_RADIUS,
    BALL_SPEED,
    BG_BOTTOM,
    BG_TOP,
    BRICK_COLORS,
    BRICK_GAP,
    BRICK_HEIGHT,
    BRICK_SCORES,
    BRICK_TOP,
    BRICK_WIDTH,
    DIM_COLOR,
    HEIGHT,
    HUD_COLOR,
    MAX_BOUNCE_ANGLE,
    STARTING_LIVES,
    WIDTH,
)

TITLE, PLAYING, PAUSED, LEVEL_COMPLETE, GAME_OVER, WIN, CUSTOM_MENU, EDITOR = range(8)
TITLE_OPTIONS = ["Play Campaign", "Custom Levels", "Level Editor", "Quit"]
PAUSE_OPTIONS = ["Resume", "Restart Level", "Restart Game", "Quit to Title"]
DESTRUCTIBLE_CHARS = "NABP"


class Game:
    def __init__(self, level_path=None):
        self.font_tiny = pygame.font.Font(None, 20)
        self.font_small = pygame.font.Font(None, 26)
        self.font_medium = pygame.font.Font(None, 42)
        self.font_large = pygame.font.Font(None, 82)
        self.level_path = level_path
        self.background = self._make_background()
        self.editor = LevelEditor(self.background, self.level_path)
        self.state = TITLE
        self.title_index = 0
        self.menu_index = 0
        self.custom_index = 0
        self.custom_offset = 0
        self.delete_confirm = False
        self.editor_return = TITLE
        self.play_mode = "campaign"
        self.campaign_levels = [dict(level) for level in LEVELS]
        self.custom_levels = load_custom_levels(self.level_path)
        self.active_levels = self.campaign_levels
        self.score = 0
        self.lives = STARTING_LIVES
        self.level_index = 0
        self.paddle = Paddle()
        self.balls = []
        self.bricks = []
        self.powerups = []
        self.particles = []
        self.ball_launched = False
        self.load_level()

    def _make_background(self):
        surface = pygame.Surface((WIDTH, HEIGHT))
        for y in range(HEIGHT):
            t = y / max(1, HEIGHT - 1)
            color = (
                int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t),
                int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t),
                int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t),
            )
            pygame.draw.line(surface, color, (0, y), (WIDTH, y))
        rng = random.Random(7)
        for _ in range(110):
            x = rng.randint(0, WIDTH - 1)
            y = rng.randint(0, HEIGHT - 1)
            shade = rng.randint(55, 115)
            radius = rng.choice([1, 1, 1, 2])
            pygame.draw.circle(surface, (shade, shade, min(255, shade + 25)), (x, y), radius)
        return surface

    def reload_custom_levels(self):
        self.custom_levels = load_custom_levels(self.level_path)
        if self.custom_levels:
            self.custom_index = max(0, min(len(self.custom_levels) - 1, self.custom_index))
        else:
            self.custom_index = 0
        self.custom_offset = 0

    def start_campaign(self):
        self.play_mode = "campaign"
        self.active_levels = self.campaign_levels
        self.score = 0
        self.lives = STARTING_LIVES
        self.level_index = 0
        self.load_level()
        self.state = PLAYING

    def start_custom_level(self, index):
        self.reload_custom_levels()
        if not self.custom_levels:
            self.state = CUSTOM_MENU
            return
        self.custom_index = max(0, min(len(self.custom_levels) - 1, index))
        self.play_mode = "custom"
        self.active_levels = [self.custom_levels[self.custom_index]]
        self.score = 0
        self.lives = STARTING_LIVES
        self.level_index = 0
        self.load_level()
        self.state = PLAYING

    def restart_run(self):
        if self.play_mode == "custom":
            self.start_custom_level(self.custom_index)
        else:
            self.start_campaign()

    def load_level(self):
        if not self.active_levels:
            return
        self.paddle.reset()
        self.bricks = []
        self.powerups = []
        self.particles = []
        self.balls = []
        self.ball_launched = False
        self.menu_index = 0
        rows = self.active_levels[self.level_index]["rows"]
        columns = max(len(row) for row in rows)
        layout_width = columns * BRICK_WIDTH + (columns - 1) * BRICK_GAP
        start_x = (WIDTH - layout_width) // 2
        for row_index, row in enumerate(rows):
            for column_index, kind in enumerate(row):
                if kind not in BRICK_COLORS:
                    continue
                x = start_x + column_index * (BRICK_WIDTH + BRICK_GAP)
                y = BRICK_TOP + row_index * (BRICK_HEIGHT + BRICK_GAP)
                self.bricks.append(Brick(x, y, kind))
        self._attach_ball()

    def _attach_ball(self):
        ball = Ball(self.paddle.rect.centerx, self.paddle.rect.top - BALL_RADIUS - 1)
        self.balls = [ball]

    def advance_level(self):
        if self.level_index + 1 >= len(self.active_levels):
            self.state = WIN
        else:
            self.level_index += 1
            self.load_level()
            self.state = PLAYING

    def open_custom_menu(self):
        self.reload_custom_levels()
        self.state = CUSTOM_MENU
        self.delete_confirm = False

    def open_editor(self, level=None, index=None, return_state=TITLE):
        self.editor_return = return_state
        if level is None:
            self.editor.new_level()
        else:
            self.editor.load_level(level, index)
        self.state = EDITOR

    def _leave_editor(self):
        self.reload_custom_levels()
        self.state = self.editor_return

    def handle_event(self, event):
        if self.state == EDITOR:
            action = self.editor.handle_event(event)
            if action == "exit":
                self._leave_editor()
            return
        if event.type != pygame.KEYDOWN:
            return
        key = event.key
        if self.state == TITLE:
            if key in (pygame.K_UP, pygame.K_w):
                self.title_index = (self.title_index - 1) % len(TITLE_OPTIONS)
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.title_index = (self.title_index + 1) % len(TITLE_OPTIONS)
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._select_title()
            elif key == pygame.K_SPACE:
                self.start_campaign()
            elif key == pygame.K_ESCAPE:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
        elif self.state == CUSTOM_MENU:
            self._handle_custom_menu_key(key)
        elif self.state == PLAYING:
            if key == pygame.K_SPACE:
                self.launch_ball()
            elif key == pygame.K_ESCAPE:
                self.state = PAUSED
                self.menu_index = 0
        elif self.state == PAUSED:
            if key == pygame.K_ESCAPE:
                self.state = PLAYING
            elif key in (pygame.K_UP, pygame.K_w):
                self.menu_index = (self.menu_index - 1) % len(PAUSE_OPTIONS)
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.menu_index = (self.menu_index + 1) % len(PAUSE_OPTIONS)
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self._select_pause()
        elif self.state == LEVEL_COMPLETE:
            if key == pygame.K_SPACE:
                if self.play_mode == "custom":
                    self.open_custom_menu()
                else:
                    self.advance_level()
        elif self.state == GAME_OVER:
            if key == pygame.K_SPACE:
                self.restart_run()
            elif key == pygame.K_ESCAPE:
                if self.play_mode == "custom":
                    self.open_custom_menu()
                else:
                    self.state = TITLE
        elif self.state == WIN:
            if key == pygame.K_SPACE:
                self.start_campaign()
            elif key == pygame.K_ESCAPE:
                self.state = TITLE

    def _select_title(self):
        option = TITLE_OPTIONS[self.title_index]
        if option == "Play Campaign":
            self.start_campaign()
        elif option == "Custom Levels":
            self.open_custom_menu()
        elif option == "Level Editor":
            self.open_editor(None, None, TITLE)
        else:
            pygame.event.post(pygame.event.Event(pygame.QUIT))

    def _handle_custom_menu_key(self, key):
        if self.delete_confirm:
            if key in (pygame.K_y, pygame.K_RETURN, pygame.K_KP_ENTER):
                if self.custom_levels:
                    del self.custom_levels[self.custom_index]
                    save_custom_levels(self.custom_levels, self.level_path)
                    self.reload_custom_levels()
                self.delete_confirm = False
            elif key in (pygame.K_n, pygame.K_ESCAPE):
                self.delete_confirm = False
            return

        if not self.custom_levels:
            if key == pygame.K_n:
                self.open_editor(None, None, CUSTOM_MENU)
            elif key == pygame.K_ESCAPE:
                self.state = TITLE
            return

        if key in (pygame.K_UP, pygame.K_w):
            self.custom_index = (self.custom_index - 1) % len(self.custom_levels)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.custom_index = (self.custom_index + 1) % len(self.custom_levels)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self.start_custom_level(self.custom_index)
        elif key == pygame.K_e:
            self.open_editor(self.custom_levels[self.custom_index], self.custom_index, CUSTOM_MENU)
        elif key == pygame.K_n:
            self.open_editor(None, None, CUSTOM_MENU)
        elif key == pygame.K_DELETE:
            self.delete_confirm = True
        elif key == pygame.K_ESCAPE:
            self.state = TITLE

    def _select_pause(self):
        option = PAUSE_OPTIONS[self.menu_index]
        if option == "Resume":
            self.state = PLAYING
        elif option == "Restart Level":
            self.load_level()
            self.state = PLAYING
        elif option == "Restart Game":
            self.restart_run()
        else:
            self.state = TITLE

    def launch_ball(self):
        if self.ball_launched or not self.balls:
            return
        self.balls[0].launch()
        self.ball_launched = True

    def update(self, dt, paddle_direction=None):
        if self.state == EDITOR:
            self.editor.update(dt)
            return
        if self.state != PLAYING:
            return

        if paddle_direction is None:
            keys = pygame.key.get_pressed()
            direction = int(keys[pygame.K_RIGHT]) - int(keys[pygame.K_LEFT])
        else:
            direction = paddle_direction
        self.paddle.update(dt)
        self.paddle.move(direction, dt)

        if self.ball_launched:
            self._update_balls(dt)
        else:
            ball = self.balls[0]
            ball.x = float(self.paddle.rect.centerx)
            ball.y = float(self.paddle.rect.top - ball.radius - 1)

        self._update_powerups(dt)
        self._update_particles(dt)

        if not self._has_destructible_bricks():
            self.score += 50
            self.state = LEVEL_COMPLETE
        elif self.ball_launched and not self.balls:
            self._lose_life()

    def _has_destructible_bricks(self):
        return any(brick.kind != "X" for brick in self.bricks)

    def _update_balls(self, dt):
        for ball in list(self.balls):
            speed = math.hypot(ball.vx, ball.vy)
            steps = max(1, min(10, int(speed * dt / (ball.radius * 0.5)) + 1))
            step_dt = dt / steps
            for _ in range(steps):
                self._step_ball(ball, step_dt)
            if ball.y - ball.radius > HEIGHT and ball in self.balls:
                self.balls.remove(ball)

    def _step_ball(self, ball, dt):
        ball.x += ball.vx * dt
        ball.y += ball.vy * dt
        radius = ball.radius

        if ball.x - radius < 0:
            ball.x = radius
            ball.vx = abs(ball.vx)
        elif ball.x + radius > WIDTH:
            ball.x = WIDTH - radius
            ball.vx = -abs(ball.vx)

        if ball.y - radius < 0:
            ball.y = radius
            ball.vy = abs(ball.vy)

        if ball.vy > 0:
            self._paddle_collision(ball)
        self._brick_collision(ball)
        clamp_ball_direction(ball)

    def _paddle_collision(self, ball):
        paddle = self.paddle.rect
        if ball.y + ball.radius < paddle.top or ball.y - ball.radius > paddle.bottom:
            return False
        if ball.x + ball.radius < paddle.left or ball.x - ball.radius > paddle.right:
            return False
        if ball.y > paddle.centery:
            return False
        offset = (ball.x - paddle.centerx) / (paddle.width / 2)
        offset = max(-1.0, min(1.0, offset))
        if abs(offset) < 0.06:
            offset = random.choice([-0.14, 0.14])
        angle = offset * MAX_BOUNCE_ANGLE
        ball.vx = math.sin(angle) * ball.speed
        ball.vy = -math.cos(angle) * ball.speed
        ball.y = paddle.top - ball.radius - 0.5
        return True

    def _brick_collision(self, ball):
        for brick in self.bricks:
            if resolve_circle_rect(ball, brick.rect):
                self._damage_brick(brick)
                return

    def _damage_brick(self, brick, chain=False):
        if brick not in self.bricks:
            return
        if brick.indestructible:
            self._spawn_particles(brick.rect.center, (196, 204, 218), 2)
            return
        brick.hp -= 1
        if brick.hp <= 0:
            self._destroy_brick(brick, chain)
        else:
            self._spawn_particles(brick.rect.center, brick.color, 4)

    def _destroy_brick(self, brick, chain=False):
        if brick in self.bricks:
            self.bricks.remove(brick)
        self.score += BRICK_SCORES.get(brick.kind, 10)
        count = 12 if brick.kind == "B" else 7
        self._spawn_particles(brick.rect.center, brick.color, count)
        if brick.kind == "P":
            kind = random.choice(["extra_ball", "widen"])
            self.powerups.append(PowerUp(brick.rect.centerx, brick.rect.centery, kind))
        if brick.kind == "B" and not brick.exploded:
            brick.exploded = True
            self._explode(brick)

    def _explode(self, source):
        radius = BRICK_WIDTH * 1.6
        center_x, center_y = source.rect.center
        for brick in list(self.bricks):
            distance = math.hypot(brick.rect.centerx - center_x, brick.rect.centery - center_y)
            if distance <= radius:
                self._damage_brick(brick, chain=True)

    def _update_powerups(self, dt):
        for powerup in list(self.powerups):
            powerup.update(dt)
            if powerup.rect.colliderect(self.paddle.rect):
                self._apply_powerup(powerup.kind)
                self.powerups.remove(powerup)
            elif powerup.rect.top > HEIGHT:
                self.powerups.remove(powerup)

    def _apply_powerup(self, kind):
        if kind == "widen":
            self.paddle.widen()
        else:
            self._spawn_extra_ball()

    def _spawn_extra_ball(self):
        angle = random.uniform(math.radians(20), math.radians(70))
        side = random.choice([-1.0, 1.0])
        vx = side * math.sin(angle) * BALL_SPEED
        vy = -math.cos(angle) * BALL_SPEED
        ball = Ball(self.paddle.rect.centerx, self.paddle.rect.top - BALL_RADIUS - 1, vx, vy)
        self.balls.append(ball)

    def _spawn_particles(self, center, color, count):
        for _ in range(count):
            if len(self.particles) >= 240:
                break
            self.particles.append(Particle(center[0], center[1], color))

    def _update_particles(self, dt):
        for particle in self.particles:
            particle.update(dt)
        self.particles = [particle for particle in self.particles if particle.alive]

    def _lose_life(self):
        self.lives -= 1
        self.powerups.clear()
        self.paddle.reset()
        if self.lives <= 0:
            self.balls = []
            self.state = GAME_OVER
        else:
            self._attach_ball()
            self.ball_launched = False

    def draw(self, surface):
        if self.state == EDITOR:
            self.editor.draw(surface)
            return
        surface.blit(self.background, (0, 0))
        if self.state == TITLE:
            self._draw_title(surface)
            return
        if self.state == CUSTOM_MENU:
            self._draw_custom_menu(surface)
            return

        for brick in self.bricks:
            brick.draw(surface, self.font_small)
        for powerup in self.powerups:
            powerup.draw(surface, self.font_small)
        self.paddle.draw(surface)
        for ball in self.balls:
            ball.draw(surface)
        for particle in self.particles:
            particle.draw(surface)

        self._draw_hud(surface)

        if self.state == PLAYING and not self.ball_launched:
            self._blit_text(
                surface,
                "Press SPACE to launch",
                self.font_small,
                DIM_COLOR,
                center=(WIDTH // 2, HEIGHT - 108),
            )

        if self.state == PAUSED:
            self._draw_pause(surface)
        elif self.state == LEVEL_COMPLETE:
            self._draw_level_complete(surface)
        elif self.state == GAME_OVER:
            self._draw_end(surface, "GAME OVER", "Press SPACE to try again")
        elif self.state == WIN:
            self._draw_end(surface, "YOU WIN!", "Press SPACE to play again")

    def _blit_text(self, surface, text, font, color, center=None, topleft=None):
        image = font.render(text, True, color)
        rect = image.get_rect()
        if center is not None:
            rect.center = center
        elif topleft is not None:
            rect.topleft = topleft
        surface.blit(image, rect)
        return rect

    def _draw_title(self, surface):
        self._blit_text(surface, "BREAKOUT", self.font_large, (8, 10, 20), center=(WIDTH // 2 + 3, 98))
        self._blit_text(surface, "BREAKOUT", self.font_large, ACCENT, center=(WIDTH // 2, 93))
        self._blit_text(
            surface,
            "Smash the bricks. Chain the explosions.",
            self.font_small,
            DIM_COLOR,
            center=(WIDTH // 2, 150),
        )

        for index, option in enumerate(TITLE_OPTIONS):
            y = 210 + index * 52
            selected = index == self.title_index
            if selected:
                box = pygame.Rect(0, 0, 360, 42)
                box.center = (WIDTH // 2, y)
                pygame.draw.rect(surface, ACCENT, box, border_radius=10)
                color = (18, 20, 32)
            else:
                color = HUD_COLOR
            self._blit_text(surface, option, self.font_medium, color, center=(WIDTH // 2, y))

        legend = [
            ("N", "Normal"),
            ("A", "Armored"),
            ("B", "Bomb"),
            ("P", "Power-up"),
            ("X", "Wall"),
        ]
        slot = 148
        start = (WIDTH - slot * len(legend)) // 2
        for index, (kind, label) in enumerate(legend):
            x = start + index * slot
            box = pygame.Rect(x + 16, 424, 28, 18)
            pygame.draw.rect(surface, (5, 6, 14), box.move(1, 2), border_radius=4)
            pygame.draw.rect(surface, BRICK_COLORS[kind], box, border_radius=4)
            pygame.draw.rect(surface, (255, 255, 255), box, width=1, border_radius=4)
            self._blit_text(surface, label, self.font_tiny, DIM_COLOR, topleft=(x + 52, 427))

        self._blit_text(
            surface,
            "UP/DOWN select    ENTER confirm    SPACE quick start",
            self.font_tiny,
            DIM_COLOR,
            center=(WIDTH // 2, 482),
        )
        self._blit_text(
            surface,
            "LEFT/RIGHT move    SPACE launch    ESC pause",
            self.font_tiny,
            DIM_COLOR,
            center=(WIDTH // 2, 508),
        )
        self._blit_text(
            surface,
            f"{len(self.campaign_levels)} built-in levels + {len(self.custom_levels)} custom",
            self.font_tiny,
            ACCENT,
            center=(WIDTH // 2, 548),
        )

    def _draw_custom_menu(self, surface):
        pygame.draw.line(surface, (52, 58, 94), (0, 45), (WIDTH, 45), 1)
        self._blit_text(surface, "CUSTOM LEVELS", self.font_small, ACCENT, topleft=(20, 12))
        self._blit_text(surface, "ESC back", self.font_tiny, DIM_COLOR, topleft=(WIDTH - 88, 17))

        list_area = pygame.Rect(28, 72, 260, 380)
        preview_area = pygame.Rect(304, 72, 468, 380)
        pygame.draw.rect(surface, (16, 20, 36), list_area, border_radius=10)
        pygame.draw.rect(surface, (48, 54, 84), list_area, width=1, border_radius=10)
        pygame.draw.rect(surface, (16, 20, 36), preview_area, border_radius=10)
        pygame.draw.rect(surface, (48, 54, 84), preview_area, width=1, border_radius=10)
        self._blit_text(surface, "SAVED LEVELS", self.font_tiny, DIM_COLOR, topleft=(list_area.left + 14, list_area.top + 10))
        self._blit_text(surface, "PREVIEW", self.font_tiny, DIM_COLOR, topleft=(preview_area.left + 14, preview_area.top + 10))

        if not self.custom_levels:
            self._blit_text(
                surface,
                "No custom levels yet",
                self.font_medium,
                HUD_COLOR,
                center=(preview_area.centerx, preview_area.centery - 20),
            )
            self._blit_text(
                surface,
                "Press N to create one in the editor",
                self.font_tiny,
                DIM_COLOR,
                center=(preview_area.centerx, preview_area.centery + 24),
            )
            self._blit_text(
                surface,
                "N new level    ESC back",
                self.font_tiny,
                ACCENT,
                center=(WIDTH // 2, 500),
            )
        else:
            visible = 10
            spacing = 32
            if self.custom_index < self.custom_offset:
                self.custom_offset = self.custom_index
            elif self.custom_index >= self.custom_offset + visible:
                self.custom_offset = self.custom_index - visible + 1
            self.custom_offset = max(0, min(self.custom_offset, max(0, len(self.custom_levels) - visible)))
            for slot in range(visible):
                index = self.custom_offset + slot
                if index >= len(self.custom_levels):
                    break
                row = pygame.Rect(list_area.left + 10, list_area.top + 38 + slot * spacing, list_area.width - 20, spacing - 4)
                if index == self.custom_index:
                    pygame.draw.rect(surface, ACCENT, row, border_radius=6)
                    color = (18, 20, 32)
                else:
                    color = HUD_COLOR
                self._blit_text(
                    surface,
                    self.custom_levels[index]["name"],
                    self.font_tiny,
                    color,
                    topleft=(row.left + 10, row.top + 6),
                )

            level = self.custom_levels[self.custom_index]
            self._blit_text(
                surface,
                level["name"],
                self.font_small,
                HUD_COLOR,
                center=(preview_area.centerx, preview_area.top + 34),
            )
            preview_rect = pygame.Rect(
                preview_area.left + 14,
                preview_area.top + 58,
                preview_area.width - 28,
                preview_area.height - 116,
            )
            draw_level_preview(surface, level["rows"], preview_rect)
            destructible = sum(1 for row in level["rows"] for char in row if char in DESTRUCTIBLE_CHARS)
            walls = sum(1 for row in level["rows"] for char in row if char == "X")
            self._blit_text(
                surface,
                f"{destructible} destructible bricks    {walls} indestructible walls",
                self.font_tiny,
                DIM_COLOR,
                center=(preview_area.centerx, preview_area.bottom - 34),
            )
            self._blit_text(
                surface,
                "ENTER play    E edit    N new    DELETE remove    ESC back",
                self.font_tiny,
                ACCENT,
                center=(WIDTH // 2, 500),
            )

        self._blit_text(
            surface,
            "Preview updates as you select a level",
            self.font_tiny,
            DIM_COLOR,
            center=(WIDTH // 2, 534),
        )

        if self.delete_confirm and self.custom_levels:
            self._draw_delete_confirm(surface)

    def _draw_delete_confirm(self, surface):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((4, 6, 16, 200))
        surface.blit(overlay, (0, 0))
        panel = pygame.Rect(0, 0, 520, 200)
        panel.center = (WIDTH // 2, HEIGHT // 2)
        pygame.draw.rect(surface, (18, 22, 40), panel, border_radius=12)
        pygame.draw.rect(surface, (60, 68, 104), panel, width=2, border_radius=12)
        name = self.custom_levels[self.custom_index]["name"]
        self._blit_text(surface, "DELETE LEVEL", self.font_medium, (255, 120, 110), center=(panel.centerx, panel.top + 42))
        self._blit_text(surface, f'Delete "{name}"?', self.font_small, HUD_COLOR, center=(panel.centerx, panel.top + 94))
        self._blit_text(
            surface,
            "Y / ENTER delete    N / ESC cancel",
            self.font_tiny,
            DIM_COLOR,
            center=(panel.centerx, panel.bottom - 34),
        )

    def _draw_hud(self, surface):
        pygame.draw.line(surface, (52, 58, 94), (0, 45), (WIDTH, 45), 1)
        self._blit_text(
            surface,
            f"SCORE {self.score:06d}",
            self.font_small,
            HUD_COLOR,
            topleft=(20, 12),
        )
        name = self.active_levels[self.level_index]["name"]
        if self.play_mode == "custom":
            label = f"CUSTOM - {name}"
        else:
            label = f"LEVEL {self.level_index + 1} - {name}"
        self._blit_text(surface, label, self.font_small, ACCENT, center=(WIDTH // 2, 24))
        self._blit_text(surface, "LIVES", self.font_tiny, DIM_COLOR, topleft=(WIDTH - 140, 17))
        for index in range(self.lives):
            center = (WIDTH - 34 - index * 20, 25)
            pygame.draw.circle(surface, BALL_COLOR, center, 6)
            pygame.draw.circle(surface, (255, 255, 255), (center[0] - 2, center[1] - 2), 2)

    def _draw_shade(self, surface, alpha=185):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((4, 6, 16, alpha))
        surface.blit(overlay, (0, 0))

    def _draw_pause(self, surface):
        self._draw_shade(surface)
        self._blit_text(surface, "PAUSED", self.font_large, HUD_COLOR, center=(WIDTH // 2, 150))
        for index, option in enumerate(PAUSE_OPTIONS):
            y = 260 + index * 54
            selected = index == self.menu_index
            if selected:
                box = pygame.Rect(0, 0, 360, 44)
                box.center = (WIDTH // 2, y)
                pygame.draw.rect(surface, ACCENT, box, border_radius=10)
                color = (18, 20, 32)
            else:
                color = HUD_COLOR
            self._blit_text(surface, option, self.font_medium, color, center=(WIDTH // 2, y))
        self._blit_text(
            surface,
            "UP/DOWN select    ENTER confirm    ESC resume",
            self.font_tiny,
            DIM_COLOR,
            center=(WIDTH // 2, HEIGHT - 64),
        )

    def _draw_level_complete(self, surface):
        self._draw_shade(surface)
        if self.play_mode == "custom":
            title = "CUSTOM LEVEL CLEARED"
            prompt = "Press SPACE to return to custom levels"
        else:
            title = f"LEVEL {self.level_index + 1} CLEARED"
            prompt = "Press SPACE to continue"
        self._blit_text(surface, title, self.font_medium, HUD_COLOR, center=(WIDTH // 2, 220))
        self._blit_text(
            surface,
            f"Score {self.score:06d}",
            self.font_small,
            ACCENT,
            center=(WIDTH // 2, 275),
        )
        if (pygame.time.get_ticks() // 450) % 2 == 0:
            self._blit_text(surface, prompt, self.font_small, HUD_COLOR, center=(WIDTH // 2, 350))

    def _draw_end(self, surface, title, prompt):
        self._draw_shade(surface)
        color = ACCENT if title == "YOU WIN!" else (255, 120, 110)
        self._blit_text(surface, title, self.font_large, color, center=(WIDTH // 2, 220))
        self._blit_text(
            surface,
            f"Final score {self.score:06d}",
            self.font_medium,
            HUD_COLOR,
            center=(WIDTH // 2, 290),
        )
        if (pygame.time.get_ticks() // 450) % 2 == 0:
            self._blit_text(surface, prompt, self.font_small, HUD_COLOR, center=(WIDTH // 2, 360))
        self._blit_text(
            surface,
            "ESC returns to menu",
            self.font_tiny,
            DIM_COLOR,
            center=(WIDTH // 2, 410),
        )
