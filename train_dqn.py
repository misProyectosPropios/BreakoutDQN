import argparse
import os
import random
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np
import pygame
import torch

from dqn import (
    DEFAULT_LEVEL_CLEAR_REWARD,
    DEFAULT_MODEL_PATH,
    DEFAULT_STEP_PENALTY,
    DEFAULT_WIN_REWARD,
    DEFAULT_WIN_SPEED_BONUS,
    BreakoutEnv,
    DQNAgent,
)
from level_gen import LevelPool, build_static_levels, generate_random_level

DEFAULT_BEST_PATH = DEFAULT_MODEL_PATH.with_name("dqn_breakout_best.pt")


def parse_args():
    parser = argparse.ArgumentParser(description="Train a DQN agent for Breakout.")
    parser.add_argument("--episodes", type=int, default=300)
    parser.add_argument("--level", type=int, default=0)
    parser.add_argument("--campaign", action="store_true")
    parser.add_argument("--levels", choices=["mixed", "builtin", "custom", "procedural"], default="mixed")
    parser.add_argument("--procedural-ratio", type=float, default=0.5)
    parser.add_argument("--custom-path", type=str, default=None)
    parser.add_argument("--max-steps", type=int, default=6000)
    parser.add_argument("--frame-skip", type=int, default=2)
    parser.add_argument("--step-penalty", type=float, default=DEFAULT_STEP_PENALTY)
    parser.add_argument("--win-speed-bonus", type=float, default=DEFAULT_WIN_SPEED_BONUS)
    parser.add_argument("--win-reward", type=float, default=DEFAULT_WIN_REWARD)
    parser.add_argument("--level-clear-reward", type=float, default=DEFAULT_LEVEL_CLEAR_REWARD)
    parser.add_argument("--save", type=str, default=str(DEFAULT_MODEL_PATH))
    parser.add_argument("--best-save", type=str, default=str(DEFAULT_BEST_PATH))
    parser.add_argument("--load", type=str, default=None)
    parser.add_argument("--save-every", type=int, default=10)
    parser.add_argument("--print-every", type=int, default=1)
    parser.add_argument("--eval-every", type=int, default=20)
    parser.add_argument("--eval-procedural", type=int, default=4)
    parser.add_argument("--eval-verbose", action="store_true")
    parser.add_argument("--warmup", type=int, default=1000)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--reset-exploration", action="store_true")
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def evaluate(agent, env, levels, max_steps, verbose=False):
    wins = 0
    winning_steps = []
    results = []
    for level in levels:
        state = env.reset(level=level)
        done = False
        steps = 0
        won = False
        while not done and steps < max_steps:
            action = agent.act(state, greedy=True)
            state, reward, done, info = env.step(action)
            won = won or info["won"]
            steps += 1
        wins += int(won)
        if won:
            winning_steps.append(steps)
        results.append((level.get("name", "Level"), level.get("source", "?"), won, steps))
        if verbose:
            print(
                f"  eval {level.get('source', '?'):10s} {level.get('name', 'Level')[:24]:24s} "
                f"won {int(won)} steps {steps:5d}",
                flush=True,
            )
    win_rate = wins / len(levels) if levels else 0.0
    average_steps = sum(winning_steps) / len(winning_steps) if winning_steps else float(max_steps)
    return win_rate, average_steps, results


def main():
    args = parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    pygame.init()

    include_builtin = args.levels in ("mixed", "builtin")
    include_custom = args.levels in ("mixed", "custom")
    static_levels, skipped = build_static_levels(
        include_builtin=include_builtin,
        include_custom=include_custom,
        custom_path=args.custom_path,
    )
    if args.levels == "procedural":
        static_levels = []

    if args.levels in ("custom",):
        procedural_ratio = 0.0
    elif args.levels == "procedural":
        procedural_ratio = 1.0
    elif args.levels in ("builtin",):
        procedural_ratio = 0.0
    else:
        procedural_ratio = args.procedural_ratio

    if not static_levels and procedural_ratio <= 0.0:
        print("No valid levels available for training.")
        pygame.quit()
        return

    pool = LevelPool(static_levels, procedural_ratio, random.Random(args.seed + 1))
    env = BreakoutEnv(
        level_index=args.level,
        frame_skip=args.frame_skip,
        max_steps=args.max_steps,
        campaign=args.campaign,
        level_pool=None if args.campaign else pool,
        step_penalty=args.step_penalty,
        win_speed_bonus=args.win_speed_bonus,
        win_reward=args.win_reward,
        level_clear_reward=args.level_clear_reward,
    )
    agent = DQNAgent(batch_size=args.batch_size, warmup=args.warmup)
    if args.load:
        agent.load(args.load, reset_exploration=args.reset_exploration)
        print(f"Loaded model from {args.load}")

    eval_levels = list(static_levels)
    eval_rng = random.Random(args.seed + 7919)
    for _ in range(args.eval_procedural):
        eval_levels.append(generate_random_level(eval_rng))

    print(
        f"Training on {len(static_levels)} static levels "
        f"(builtin={include_builtin}, custom={include_custom}) "
        f"with procedural ratio {procedural_ratio:.2f}"
    )
    if skipped:
        print(f"Skipped unsolvable levels: {', '.join(skipped)}")
    if eval_levels:
        print(f"Evaluation set: {len(eval_levels)} levels")
    print(
        f"Reward: brick +0.3 | step -{args.step_penalty:.4f} | life -5 | "
        f"level clear +{args.level_clear_reward:.2f} | "
        f"win +{args.win_reward:.2f} (+{args.win_speed_bonus:.2f} speed bonus)"
    )

    best_reward = float("-inf")
    best_win_rate = -1.0
    best_average_steps = float("inf")
    started = time.time()

    for episode in range(1, args.episodes + 1):
        state = env.reset()
        level = env.current_level if env.current_level else {}
        level_name = level.get("name", "Level")
        level_source = level.get("source", "?")
        total_reward = 0.0
        total_destroyed = 0
        steps = 0
        won = False
        losses = []
        done = False

        while not done:
            action = agent.act(state)
            next_state, reward, done, info = env.step(action)
            agent.remember(state, action, reward, next_state, done)
            loss = agent.train_step()
            if loss is not None:
                losses.append(loss)
            state = next_state
            total_reward += reward
            total_destroyed += info["bricks_destroyed"]
            won = won or info["won"]
            steps += 1

        if total_reward > best_reward:
            best_reward = total_reward

        should_print = episode == 1 or episode % args.print_every == 0
        if should_print:
            average_loss = sum(losses) / len(losses) if losses else 0.0
            elapsed = time.time() - started
            print(
                f"episode {episode:04d} | {level_source:10s} {level_name[:20]:20s} | "
                f"reward {total_reward:7.2f} | bricks {total_destroyed:3d} | steps {steps:5d} | "
                f"epsilon {agent.epsilon:.3f} | loss {average_loss:.4f} | won {int(won)} | "
                f"best {best_reward:7.2f} | {elapsed:6.1f}s",
                flush=True,
            )

        if args.eval_every > 0 and eval_levels and (
            episode % args.eval_every == 0 or episode == args.episodes
        ):
            win_rate, average_steps, results = evaluate(
                agent,
                env,
                eval_levels,
                args.max_steps,
                verbose=args.eval_verbose,
            )
            improved = win_rate > best_win_rate or (
                win_rate == best_win_rate and average_steps < best_average_steps
            )
            if improved:
                best_win_rate = win_rate
                best_average_steps = average_steps
                agent.save(args.best_save)
            wins_count = sum(1 for _, _, won, _ in results if won)
            steps_label = f"{average_steps:7.1f}" if wins_count else "    n/a"
            print(
                f"eval @ episode {episode:04d} | win {wins_count}/{len(results)} "
                f"({win_rate * 100:5.1f}%) | avg win steps {steps_label} | "
                f"best {best_win_rate * 100:5.1f}% @ {best_average_steps:7.1f} steps"
                + (" | saved best" if improved else ""),
                flush=True,
            )

        if args.save_every > 0 and episode % args.save_every == 0:
            agent.save(args.save)

    agent.save(args.save)
    pygame.quit()
    print(f"Model saved to {args.save}")
    if best_win_rate >= 0:
        print(f"Best model saved to {args.best_save}")


if __name__ == "__main__":
    main()
