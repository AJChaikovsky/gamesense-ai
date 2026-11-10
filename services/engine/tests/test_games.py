import pytest
from gamesense.games import GENERIC, detect_game, game_by_id


def test_detect_known_games() -> None:
    assert detect_game("cs2.exe", "Counter-Strike 2").game_id == "cs2"
    assert detect_game("eldenring.exe", "ELDEN RING").game_id == "fromsoft_rpg"
    assert detect_game("javaw.exe", "Minecraft 1.21.4").game_id == "minecraft"


def test_java_without_minecraft_title_is_generic() -> None:
    assert detect_game("javaw.exe", "Some IDE") is GENERIC


def test_riot_titles_block_live_coaching() -> None:
    game = detect_game("VALORANT-Win64-Shipping.exe", "VALORANT")
    assert game.game_id == "valorant" and not game.live_allowed
    assert game.policy_reason


def test_game_by_id() -> None:
    assert game_by_id("minecraft").genre == "sandbox"
    with pytest.raises(ValueError):
        game_by_id("nope")


def test_pick_window_skips_launchers_and_terminals() -> None:
    from gamesense.games.foreground import WindowCandidate, pick_window

    launcher = WindowCandidate("Minecraft Launcher", "MinecraftLauncher.exe", 1, 1_000_000)
    shell = WindowCandidate("uv run gamesense-eval --window Minecraft", "WindowsTerminal.exe", 2, 9)
    game = WindowCandidate("Minecraft 1.21.4", "javaw.exe", 3, 500_000)
    assert pick_window("Minecraft", [launcher, shell, game]) == game
    assert pick_window("minecraft launcher", [launcher, game]) == launcher
    assert pick_window("Minecraft", [launcher, shell]) is None
    assert pick_window("", [game]) is None


def test_pick_window_prefers_exact_title_then_largest() -> None:
    from gamesense.games.foreground import WindowCandidate, pick_window

    small = WindowCandidate("Counter-Strike 2", "cs2.exe", 1, 100)
    big = WindowCandidate("Counter-Strike 2 - Workshop", "steamwebhelper.exe", 2, 10_000)
    assert pick_window("counter-strike 2", [big, small]) == small
    assert pick_window("Counter", [small, big]) == big
