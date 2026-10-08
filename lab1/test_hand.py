"""Lab 1: check the hand simulation with random actions."""


def main(render_mode="human", steps=500):
    import gymnasium as gym
    import gymnasium_robotics

    # Register the robotics environments before creating the hand demo.
    gym.register_envs(gymnasium_robotics)
    env = gym.make("HandManipulateBlock-v1", render_mode=render_mode)
    try:
        env.reset()
        print(">>> Initializing the hand demo. Press Ctrl+C to exit.")
        for _ in range(steps):
            action = env.action_space.sample()
            _, _, terminated, truncated, _ = env.step(action)
            if render_mode is not None:
                env.render()
            if terminated or truncated:
                env.reset()
        print(">>> Verification complete: the hand simulation ran successfully.")
    except KeyboardInterrupt:
        print(">>> Hand demo stopped.")
    finally:
        env.close()


if __name__ == "__main__":
    main()
