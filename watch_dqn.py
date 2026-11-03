import argparse
import random

import pygame

from dqn import (
    DEFAULT_LEVEL_CLEAR_REWARD,
    DEFAULT_MODEL_PATH,
    DEFAULT_STEP_PENALTY,
    DEFAULT_WIN_REWARD,
    DEFAULT_WIN_SPEED_BONUS,
    BreakoutEnv,
    DQNAgent,
)
from level_gen import LevelPool, build_static_levels
from settings import FPS, HEIGHT, WIDTH


def parse_args():
    parser = argparse.ArgumentParser(description="Watch a trained DQN play Breakout.")
    parser.add_argument("--model", type=str, default=str(DEFAULT_MODEL_PATH))
    parser.add_argument("--level", type=int, default=0)
    parser.add_argument(
        "--level-name",
        type=str,
        default=None,
        help="Pick a static level by name (case-insensitive). Searches both "
             "builtin and custom levels regardless of --levels. Overrides --level.",
    )
    parser.add_argument("--campaign", action="store_true")
    parser.add_argument("--levels", choices=["mixed", "builtin", "custom", "procedural"], default="builtin")
    parser.add_argument("--procedural-ratio", type=float, default=0.5)
    parser.add_argument("--custom-path", type=str, default=None)
    parser.add_argument("--episodes", type=int, default=0)
    parser.add_argument("--max-steps", type=int, default=6000)
    parser.add_argument("--frame-skip", type=int, default=1)
    parser.add_argument("--step-penalty", type=float, default=DEFAULT_STEP_PENALTY)
    parser.add_argument("--win-speed-bonus", type=float, default=DEFAULT_WIN_SPEED_BONUS)
    parser.add_argument("--win-reward", type=float, default=DEFAULT_WIN_REWARD)
    parser.add_argument("--level-clear-reward", type=float, default=DEFAULT_LEVEL_CLEAR_REWARD)
    parser.add_argument("--seed", type=int, default=None)
    return parser.parse_args()


def resolve_level_index(levels, name):
    """Return the index of the level matching `name` (case-insensitive), or None.

    If several levels share the same name, the first match is used and a
    warning is printed so the caller knows the choice was ambiguous.
    """
    target = name.strip().lower()
    matches = [
        (idx, lvl)
        for idx, lvl in enumerate(levels)
        if lvl.get("name", "").strip().lower() == target
    ]
    if not matches:
        return None
    if len(matches) > 1:
        sources = ", ".join(lvl.get("source", "?") for _, lvl in matches)
        print(f"Warning: multiple levels match '{name}' ({sources}); using the first.")
    return matches[0][0]


def main():
    args = parse_args()
    random.seed(args.seed)
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Breakout - DQN")
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 24)

    if args.campaign:
        if args.level_name is not None:
            print("--level-name cannot be used with --campaign.")
            pygame.quit()
            return
        env = BreakoutEnv(
            level_index=args.level,
            frame_skip=args.frame_skip,
            max_steps=args.max_steps,
            campaign=True,
            step_penalty=args.step_penalty,
            win_speed_bonus=args.win_speed_bonus,
            win_reward=args.win_reward,
            level_clear_reward=args.level_clear_reward,
        )
    else:
        if args.level_name is not None:
            if args.levels == "procedural":
                print("--level-name cannot be used with --levels procedural.")
                pygame.quit()
                return
            # Force both sources so a name lookup works for builtin *and*
            # custom levels without the caller having to remember --levels.
            include_builtin = True
            include_custom = True
        else:
            include_builtin = args.levels in ("mixed", "builtin")
            include_custom = args.levels in ("mixed", "custom")

        static_levels, skipped = build_static_levels(
            include_builtin=include_builtin,
            include_custom=include_custom,
            custom_path=args.custom_path,
        )

        if args.level_name is not None:
            if not static_levels:
                print("No static levels available to match by name.")
                pygame.quit()
                return
            resolved = resolve_level_index(static_levels, args.level_name)
            if resolved is None:
                available = ", ".join(
                    f"{lvl.get('source', '?')}:{lvl.get('name', '?')}"
                    for lvl in static_levels
                ) or "(none)"
                print(f"No level named '{args.level_name}'. Available: {available}")
                pygame.quit()
                return
            # Truncate to the resolved level and start at index 0 in the pool.
            static_levels = [static_levels[resolved]]
            level_index = 0
        else:
            level_index = args.level
            if args.levels in ("builtin", "custom") and static_levels:
                index = max(0, min(len(static_levels) - 1, level_index))
                static_levels = [static_levels[index]]

        if args.levels == "procedural":
            static_levels = []
        if args.levels in ("builtin", "custom"):
            ratio = 0.0
        elif args.levels == "procedural":
            ratio = 1.0
        else:
            ratio = args.procedural_ratio

        if not static_levels and ratio <= 0.0:
            print("No levels available to watch.")
            pygame.quit()
            return
        if skipped:
            print(f"Skipped unsolvable levels: {', '.join(skipped)}")
        pool = LevelPool(static_levels, ratio, random.Random(args.seed))
        env = BreakoutEnv(
            level_index=level_index,
            frame_skip=args.frame_skip,
            max_steps=args.max_steps,
            level_pool=pool,
            step_penalty=args.step_penalty,
            win_speed_bonus=args.win_speed_bonus,
            win_reward=args.win_reward,
            level_clear_reward=args.level_clear_reward,
        )

    agent = DQNAgent()
    try:
        agent.load(args.model)
    except FileNotFoundError:
        print(f"No model found at {args.model}")
        print("Train one first with: python train_dqn.py")
        pygame.quit()
        return

    state = env.reset()
    running = True
    episodes = 0
    episode_reward = 0.0
    while running:
        clock.tick(FPS)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        action = agent.act(state, greedy=True)
        state, reward, done, info = env.step(action)
        episode_reward += reward
        env.game.draw(screen)
        level = env.current_level if env.current_level else {}
        name = level.get("name", "Level")[:32]
        source = level.get("source", "")
        label = font.render(
            f"DQN | {source}: {name} | total reward {episode_reward:+.2f}",
            True,
            (255, 206, 84),
        )
        screen.blit(label, (20, HEIGHT - 28))
        pygame.display.flip()

        if done:
            episodes += 1
            if args.episodes and episodes >= args.episodes:
                running = False
            else:
                pygame.time.wait(900)
                state = env.reset()
                episode_reward = 0.0

    pygame.quit()


if __name__ == "__main__":
    main()