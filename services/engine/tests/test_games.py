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
