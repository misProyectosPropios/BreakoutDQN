import math
import random

import pygame

from settings import (
    BALL_COLOR,
    BALL_MAX_SPEED,
    BALL_RADIUS,
    BALL_SPEED,
    BRICK_COLORS,
    BRICK_HEIGHT,
    BRICK_RADIUS,
    BRICK_WIDTH,
    PADDLE_COLOR,
    PADDLE_HEIGHT,
    PADDLE_SPEED,
    PADDLE_WIDE_MULT,
    PADDLE_WIDE_TIME,
    PADDLE_WIDTH,
    PADDLE_Y,
    POWERUP_EXTRA_COLOR,
    POWERUP_SIZE,
    POWERUP_SPEED,
    POWERUP_WIDE_COLOR,
    WIDTH,
)


class Paddle:
    def __init__(self):
        self.base_width = PADDLE_WIDTH
        self.rect = pygame.Rect(0, PADDLE_Y, PADDLE_WIDTH, PADDLE_HEIGHT)
        self.rect.centerx = WIDTH // 2
        self.wide_timer = 0.0

    def reset(self):
        self.rect.width = self.base_width
        self.rect.centerx = WIDTH // 2
        self.rect.y = PADDLE_Y
        self.wide_timer = 0.0

    def move(self, direction, dt):
        self.rect.x += direction * PADDLE_SPEED * dt
        self.rect.x = max(0, min(WIDTH - self.rect.width, self.rect.x))

    def widen(self):
        center = self.rect.centerx
        self.rect.width = int(self.base_width * PADDLE_WIDE_MULT)
        self.rect.centerx = center
        self.rect.x = max(0, min(WIDTH - self.rect.width, self.rect.x))
        self.wide_timer = PADDLE_WIDE_TIME

    def update(self, dt):
        if self.wide_timer > 0:
            self.wide_timer -= dt
            if self.wide_timer <= 0:
                center = self.rect.centerx
                self.rect.width = self.base_width
                self.rect.centerx = center
                self.rect.x = max(0, min(WIDTH - self.rect.width, self.rect.x))
                self.wide_timer = 0.0

    def draw(self, surface):
        color = (255, 196, 92) if self.wide_timer > 0 else PADDLE_COLOR
        pygame.draw.rect(surface, (8, 10, 20), self.rect.move(0, 3), border_radius=7)
        pygame.draw.rect(surface, color, self.rect, border_radius=7)
        highlight = self.rect.inflate(-8, -8)
        if highlight.height > 0 and highlight.width > 0:
            pygame.draw.rect(surface, (255, 255, 255), highlight, width=1, border_radius=4)


class Ball:
    def __init__(self, x, y, vx=0.0, vy=0.0, speed=BALL_SPEED):
        self.x = float(x)
        self.y = float(y)
        self.vx = float(vx)
        self.vy = float(vy)
        self.radius = BALL_RADIUS
        self.speed = speed
        self.color = BALL_COLOR

    def launch(self):
        angle = random.uniform(math.radians(-35), math.radians(35))
        self.vx = math.sin(angle) * self.speed
        self.vy = -math.cos(angle) * self.speed

    def normalize(self):
        magnitude = math.hypot(self.vx, self.vy)
        speed = min(self.speed, BALL_MAX_SPEED)
        if magnitude < 1e-6:
            self.vx = 0.0
            self.vy = -speed
        else:
            self.vx = self.vx / magnitude * speed
            self.vy = self.vy / magnitude * speed

    def draw(self, surface):
        center = (int(self.x), int(self.y))
        glow = pygame.Surface((self.radius * 4, self.radius * 4), pygame.SRCALPHA)
        pygame.draw.circle(glow, (255, 250, 220, 45), (self.radius * 2, self.radius * 2), self.radius * 2)
        surface.blit(glow, (center[0] - self.radius * 2, center[1] - self.radius * 2))
        pygame.draw.circle(surface, self.color, center, self.radius)
        pygame.draw.circle(surface, (255, 255, 255), (center[0] - 2, center[1] - 2), max(1, self.radius // 3))


class Brick:
    def __init__(self, x, y, kind):
        self.rect = pygame.Rect(x, y, BRICK_WIDTH, BRICK_HEIGHT)
        self.kind = kind
        self.indestructible = kind == "X"
        self.max_hp = 2 if kind == "A" else 1
        self.hp = self.max_hp
        self.color = BRICK_COLORS[kind]
        self.exploded = False

    def draw(self, surface, font):
        if self.kind == "A" and self.hp < self.max_hp:
            color = (246, 172, 72)
        else:
            color = self.color
        pygame.draw.rect(surface, (5, 6, 14), self.rect.move(2, 3), border_radius=BRICK_RADIUS)
        pygame.draw.rect(surface, color, self.rect, border_radius=BRICK_RADIUS)
        edge = tuple(min(255, channel + 60) for channel in color)
        pygame.draw.rect(surface, edge, self.rect, width=2, border_radius=BRICK_RADIUS)
        inner = self.rect.inflate(-12, -12)
        if self.kind == "B":
            pygame.draw.circle(surface, (255, 226, 150), inner.center, max(3, inner.height // 2))
            pygame.draw.circle(surface, (120, 30, 20), inner.center, max(1, inner.height // 5))
        elif self.kind == "P":
            label = font.render("?", True, (8, 40, 24))
            surface.blit(label, label.get_rect(center=self.rect.center))
        elif self.kind == "X":
            pygame.draw.rect(surface, (178, 186, 202), inner, width=1, border_radius=3)
            for point in (
                (inner.left + 3, inner.top + 3),
                (inner.right - 3, inner.top + 3),
                (inner.left + 3, inner.bottom - 3),
                (inner.right - 3, inner.bottom - 3),
            ):
                pygame.draw.circle(surface, (196, 204, 218), point, 1)
        elif self.kind == "A" and self.hp > 1:
            pygame.draw.rect(surface, (225, 205, 255), inner, width=1, border_radius=3)
        else:
            pygame.draw.rect(surface, (230, 240, 255), inner, width=1, border_radius=3)


class PowerUp:
    def __init__(self, x, y, kind):
        self.rect = pygame.Rect(0, 0, POWERUP_SIZE, POWERUP_SIZE)
        self.rect.center = (int(x), int(y))
        self.y = float(self.rect.centery)
        self.kind = kind
        self.vy = POWERUP_SPEED
        if kind == "extra_ball":
            self.color = POWERUP_EXTRA_COLOR
            self.label = "+"
        else:
            self.color = POWERUP_WIDE_COLOR
            self.label = "W"

    def update(self, dt):
        self.y += self.vy * dt
        self.rect.centery = int(self.y)

    def draw(self, surface, font):
        pygame.draw.rect(surface, (5, 6, 14), self.rect.move(2, 3), border_radius=7)
        pygame.draw.rect(surface, self.color, self.rect, border_radius=7)
        pygame.draw.rect(surface, (255, 255, 255), self.rect, width=2, border_radius=7)
        label = font.render(self.label, True, (10, 16, 24))
        surface.blit(label, label.get_rect(center=self.rect.center))


class Particle:
    def __init__(self, x, y, color):
        self.x = float(x)
        self.y = float(y)
        angle = random.uniform(0, math.tau)
        speed = random.uniform(70, 280)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.life = random.uniform(0.25, 0.6)
        self.max_life = self.life
        self.color = color
        self.size = random.randint(2, 4)

    @property
    def alive(self):
        return self.life > 0

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 430 * dt
        self.vx *= max(0.0, 1 - 2.2 * dt)
        self.life -= dt

    def draw(self, surface):
        ratio = max(0.0, self.life / self.max_life)
        radius = max(1, int(self.size * ratio) + 1)
        pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), radius)


def resolve_circle_rect(ball, rect):
    closest_x = max(rect.left, min(ball.x, rect.right))
    closest_y = max(rect.top, min(ball.y, rect.bottom))
    dx = ball.x - closest_x
    dy = ball.y - closest_y
    distance_sq = dx * dx + dy * dy
    radius = ball.radius
    if distance_sq > radius * radius:
        return False

    if distance_sq > 1e-9:
        distance = math.sqrt(distance_sq)
        nx = dx / distance
        ny = dy / distance
        ball.x = closest_x + nx * radius
        ball.y = closest_y + ny * radius
    else:
        left = ball.x - rect.left
        right = rect.right - ball.x
        top = ball.y - rect.top
        bottom = rect.bottom - ball.y
        smallest = min(left, right, top, bottom)
        if smallest == left:
            nx, ny = -1.0, 0.0
            ball.x = rect.left - radius
        elif smallest == right:
            nx, ny = 1.0, 0.0
            ball.x = rect.right + radius
        elif smallest == top:
            nx, ny = 0.0, -1.0
            ball.y = rect.top - radius
        else:
            nx, ny = 0.0, 1.0
            ball.y = rect.bottom + radius

    dot = ball.vx * nx + ball.vy * ny
    if dot < 0:
        ball.vx -= 2 * dot * nx
        ball.vy -= 2 * dot * ny
    ball.normalize()
    return True


def clamp_ball_direction(ball):
    min_vx = ball.speed * 0.16
    min_vy = ball.speed * 0.22
    changed = False
    if abs(ball.vx) < min_vx:
        sign = 1.0 if ball.vx > 0 else -1.0
        if ball.vx == 0:
            sign = random.choice([-1.0, 1.0])
        ball.vx = sign * min_vx
        changed = True
    if abs(ball.vy) < min_vy:
        sign = 1.0 if ball.vy > 0 else -1.0
        if ball.vy == 0:
            sign = -1.0
        ball.vy = sign * min_vy
        changed = True
    if changed:
        ball.normalize()
