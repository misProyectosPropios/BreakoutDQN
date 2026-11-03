import random
from collections import deque
from pathlib import Path

import numpy as np
import pygame
import torch
from torch import nn

from game import GAME_OVER, LEVEL_COMPLETE, PLAYING, WIN, Game
from settings import (
    BRICK_GAP,
    BRICK_HEIGHT,
    BRICK_TOP,
    BRICK_WIDTH,
    EDITOR_COLS,
    EDITOR_ROWS,
    FPS,
    HEIGHT,
    STARTING_LIVES,
    WIDTH,
)

# --- CHANGED: state now = grid (121) + 3 features × STACK_SIZE (12) = 133 dims ---
STACK_SIZE = 4
STATE_SIZE = EDITOR_ROWS * EDITOR_COLS + 3 * STACK_SIZE
ACTION_COUNT = 3
DEFAULT_MODEL_PATH = Path(__file__).with_name("dqn_breakout.pt")
DEFAULT_WIN_REWARD = 20.0
DEFAULT_LEVEL_CLEAR_REWARD = 5.0
DEFAULT_STEP_PENALTY = 0.002
DEFAULT_WIN_SPEED_BONUS = 2.0


class BreakoutEnv:
    def __init__(
        self,
        level_index=0,
        frame_skip=4,
        max_steps=6000,
        campaign=False,
        level_pool=None,
        step_penalty=DEFAULT_STEP_PENALTY,
        win_speed_bonus=DEFAULT_WIN_SPEED_BONUS,
        win_reward=DEFAULT_WIN_REWARD,
        level_clear_reward=DEFAULT_LEVEL_CLEAR_REWARD,
    ):
        if not pygame.get_init():
            pygame.init()
        self.game = Game()
        self.level_index = level_index
        self.frame_skip = frame_skip
        self.max_steps = max_steps
        self.campaign = campaign
        self.level_pool = level_pool
        self.step_penalty = step_penalty
        self.win_speed_bonus = win_speed_bonus
        self.win_reward = win_reward
        self.level_clear_reward = level_clear_reward
        self.steps = 0
        self.start_x = 0
        self.columns = EDITOR_COLS
        self.current_level = None
        # --- NEW: rolling window of the last STACK_SIZE dynamics snapshots ---
        self.stack_size = STACK_SIZE
        self.frame_stack = deque(maxlen=STACK_SIZE)

    def _update_geometry(self):
        game = self.game
        self.current_level = game.active_levels[game.level_index]
        rows = self.current_level["rows"]
        self.columns = max(len(row) for row in rows)
        layout_width = self.columns * BRICK_WIDTH + (self.columns - 1) * BRICK_GAP
        self.start_x = (WIDTH - layout_width) // 2

    def reset(self, level_index=None, level=None):
        if level_index is not None:
            self.level_index = level_index
        self.level_index = max(0, min(len(self.game.campaign_levels) - 1, self.level_index))
        game = self.game
        game.play_mode = "campaign"
        if level is not None:
            game.active_levels = [level]
            game.level_index = 0
        elif self.level_pool is not None:
            game.active_levels = [self.level_pool.sample()]
            game.level_index = 0
        elif self.campaign:
            game.active_levels = game.campaign_levels
            game.level_index = 0
        else:
            game.active_levels = [game.campaign_levels[self.level_index]]
            game.level_index = 0
        game.score = 0
        game.lives = STARTING_LIVES
        game.load_level()
        game.state = PLAYING
        game.launch_ball()
        self._update_geometry()
        self.steps = 0
        # --- NEW: wipe history so the agent starts from a clean window ---
        self.frame_stack.clear()
        return self.get_state()

    def _brick_code(self, brick):
        if brick.kind == "N":
            return 1
        if brick.kind == "B":
            return 2
        if brick.kind == "P":
            return 3
        if brick.kind == "A":
            return 4 if brick.hp >= brick.max_hp else 5
        if brick.kind == "X":
            return 6
        return 0

    # --- NEW: grid is the static part of the state, computed once per step ---
    def _grid(self):
        grid = np.zeros((EDITOR_ROWS, EDITOR_COLS), dtype=np.float32)
        for brick in self.game.bricks:
            row = int(round((brick.rect.y - BRICK_TOP) / (BRICK_HEIGHT + BRICK_GAP)))
            column = int(round((brick.rect.x - self.start_x) / (BRICK_WIDTH + BRICK_GAP)))
            if 0 <= row < EDITOR_ROWS and 0 <= column < EDITOR_COLS:
                grid[row, column] = self._brick_code(brick)
        return (grid / 6.0).reshape(-1)

    # --- NEW: dynamics snapshot — the three time-varying features ---
    def _snapshot(self):
        if self.game.balls:
            ball = max(self.game.balls, key=lambda item: item.y)
            ball_x = ball.x / WIDTH
            ball_y = ball.y / HEIGHT
        else:
            ball_x = 0.0
            ball_y = 0.0
        paddle_x = self.game.paddle.rect.centerx / WIDTH
        return np.array([ball_x, ball_y, paddle_x], dtype=np.float32)

    def get_state(self):
        # pad the window with copies of the earliest frame right after reset
        if not self.frame_stack:
            self.frame_stack.append(self._snapshot())
        while len(self.frame_stack) < self.stack_size:
            self.frame_stack.append(self.frame_stack[0])
        return np.concatenate([self._grid(), *self.frame_stack])

    def step(self, action):
        game = self.game
        if game.state != PLAYING:
            return self.get_state(), 0.0, True, {
                "bricks_destroyed": 0,
                "lives": game.lives,
                "won": False,
                "score": game.score,
                "steps": self.steps,
            }
        if action not in (0, 1, 2):
            raise ValueError("action must be 0, 1 or 2")
        if not game.ball_launched:
            game.launch_ball()
        bricks_before = len(game.bricks)
        lives_before = game.lives
        direction = action - 1
        game.update(self.frame_skip / FPS, direction)
        destroyed = max(0, bricks_before - len(game.bricks))
        reward = 0.3 * destroyed - self.step_penalty
        if game.lives < lives_before:
            reward -= 5.0
        won = game.state == WIN
        if game.state == LEVEL_COMPLETE:
            if self.campaign:
                game.advance_level()
                if game.state == WIN:
                    won = True
                else:
                    reward += self.level_clear_reward
                    self._update_geometry()
                    # --- NEW: start a fresh window for the next campaign level ---
                    self.frame_stack.clear()
            else:
                won = True
        self.steps += 1
        # --- NEW: push this step's snapshot (deque auto-evicts the oldest) ---
        self.frame_stack.append(self._snapshot())
        if won:
            speed_ratio = max(0.0, 1.0 - self.steps / max(1, self.max_steps))
            reward += self.win_reward + self.win_speed_bonus * speed_ratio
        done = won or game.state == GAME_OVER
        if not done and self.steps >= self.max_steps:
            done = True
        level = game.active_levels[game.level_index]
        info = {
            "bricks_destroyed": destroyed,
            "lives": game.lives,
            "won": won,
            "score": game.score,
            "steps": self.steps,
            "level_name": level.get("name", "Level"),
            "level_source": level.get("source", "unknown"),
        }
        return self.get_state(), float(reward), done, info


class QNetwork(nn.Module):
    def __init__(self, state_size=STATE_SIZE, action_count=ACTION_COUNT, hidden=256):
        super().__init__()
        self.layers = nn.Sequential(
            nn.Linear(state_size, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, action_count),
        )

    def forward(self, inputs):
        return self.layers(inputs)


class DQNAgent:
    def __init__(
        self,
        state_size=STATE_SIZE,
        action_count=ACTION_COUNT,
        device=None,
        learning_rate=1e-4,
        gamma=0.99,
        buffer_size=500_000,
        batch_size=128,
        warmup=50_000,
        target_sync=5_000,
        epsilon_start=1.0,
        epsilon_end=0.05,
        epsilon_decay_steps=10000000,
    ):
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(device)
        self.state_size = state_size
        self.action_count = action_count
        self.gamma = gamma
        self.batch_size = batch_size
        self.warmup = warmup
        self.target_sync = target_sync
        self.epsilon_start = epsilon_start
        self.epsilon_end = epsilon_end
        self.epsilon_decay_steps = epsilon_decay_steps
        self.epsilon = epsilon_start
        self.q_network = QNetwork(state_size, action_count).to(self.device)
        self.target_network = QNetwork(state_size, action_count).to(self.device)
        self.target_network.load_state_dict(self.q_network.state_dict())
        self.target_network.eval()
        self.optimizer = torch.optim.Adam(self.q_network.parameters(), lr=learning_rate)
        self.buffer = deque(maxlen=buffer_size)
        self.act_steps = 0
        self.train_steps = 0

    def act(self, state, greedy=False):
        if not greedy:
            self.act_steps += 1
            progress = min(1.0, self.act_steps / max(1, self.epsilon_decay_steps))
            self.epsilon = self.epsilon_start + (self.epsilon_end - self.epsilon_start) * progress
            if random.random() < self.epsilon:
                return random.randrange(self.action_count)
        with torch.no_grad():
            tensor = torch.as_tensor(state, dtype=torch.float32, device=self.device).unsqueeze(0)
            return int(self.q_network(tensor).argmax(dim=1).item())

    def remember(self, state, action, reward, next_state, done):
        self.buffer.append(
            (
                np.asarray(state, dtype=np.float32),
                int(action),
                float(reward),
                np.asarray(next_state, dtype=np.float32),
                bool(done),
            )
        )

    def train_step(self):
        if len(self.buffer) < max(self.batch_size, self.warmup):
            return None
        batch = random.sample(self.buffer, self.batch_size)
        states, actions, rewards, next_states, dones = zip(*batch)
        states = torch.as_tensor(np.stack(states), dtype=torch.float32, device=self.device)
        actions = torch.as_tensor(actions, dtype=torch.long, device=self.device)
        rewards = torch.as_tensor(rewards, dtype=torch.float32, device=self.device)
        next_states = torch.as_tensor(np.stack(next_states), dtype=torch.float32, device=self.device)
        dones = torch.as_tensor(dones, dtype=torch.float32, device=self.device)
        current_q = self.q_network(states).gather(1, actions.unsqueeze(1)).squeeze(1)
        with torch.no_grad():
            # The online network selects the best action
            next_actions = self.q_network(next_states).argmax(dim=1)
            # The target network evaluates that action's Q-value
            next_q = self.target_network(next_states).gather(1, next_actions.unsqueeze(1)).squeeze(1)
            targets = rewards + self.gamma * next_q * (1.0 - dones)
        loss = nn.functional.smooth_l1_loss(current_q, targets)
        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.q_network.parameters(), 10.0)
        self.optimizer.step()
        self.train_steps += 1
        if self.train_steps % self.target_sync == 0:
            self.target_network.load_state_dict(self.q_network.state_dict())
        return float(loss.item())

    def save(self, path=DEFAULT_MODEL_PATH):
        target = Path(path)
        torch.save(
            {
                "state_size": self.state_size,
                "action_count": self.action_count,
                "q_network": self.q_network.state_dict(),
                "optimizer": self.optimizer.state_dict(),
                "act_steps": self.act_steps,
                "train_steps": self.train_steps,
            },
            target,
        )
        return target

    def load(self, path=DEFAULT_MODEL_PATH, reset_exploration=False):
        source = Path(path)
        if not source.exists():
            raise FileNotFoundError(f"Model not found: {source}")
        data = torch.load(source, map_location=self.device, weights_only=False)
        self.q_network.load_state_dict(data["q_network"])
        self.target_network.load_state_dict(data["q_network"])
        if "optimizer" in data:
            self.optimizer.load_state_dict(data["optimizer"])
        self.act_steps = int(data.get("act_steps", 0))
        self.train_steps = int(data.get("train_steps", 0))
        if reset_exploration:
            self.act_steps = 0
            self.epsilon = self.epsilon_start
        else:
            self.epsilon = self.epsilon_end
        return source