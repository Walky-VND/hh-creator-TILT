from decimal import Decimal
from pathlib import Path

import pytest

from hh_creator.hh import HandHistory, Position, Street
from hh_creator.util import ActionType


@pytest.mark.parametrize("file_name", ["hu1.hh", "hu2.hh"])
def test_hu_player_order(file_name: str) -> None:
    hh = HandHistory.from_json((Path(__file__).parent / file_name).read_text())
    streets = set()
    for action in hh.actions:
        if action.street in streets:
            continue
        streets.add(action.street)
        first_player_for_street = action.player
        if action.street <= Street.PRE_FLOP:
            assert first_player_for_street.position == Position.SB, action.street
        else:
            assert action.player.position == Position.BB, action.street


@pytest.mark.parametrize("file_name", ["fold_flop.hh", "fold_preflop.hh"])
def test_remaining_action(file_name: str) -> None:
    hh = HandHistory.from_json((Path(__file__).parent / file_name).read_text())
    assert hh.n_pseudo_actions() == 0


def test_allin_ante():
    hh = HandHistory(
        [
            Decimal("22.1"),
            Decimal("22.1"),
            Decimal("22.1"),
            Decimal("8.1"),
            Decimal("22.1"),
            Decimal("22.1"),
        ],
        ante=Decimal("0.125"),
    )
    hh.post_blinds_and_antes()
    hh.add_action(ActionType.FOLD)
    hh.add_action(ActionType.RAISE, Decimal("6.975"))
    hh.add_action(ActionType.FOLD)
    hh.add_action(ActionType.RAISE, Decimal("8.025"))
    min_raise = hh.minimum_raise()
    min_bet = min(
        min_raise + hh.current_player_amount_to_call() + hh.current_player_street_bet(),
        hh.current_player.stack,
    )
    adjusted = min_bet - hh.current_player_amount_to_call()
    hh.add_action(ActionType.RAISE, adjusted)


def test_shove_after_3bet_over_4bet():
    """Regression: a player who 3-bet and then shoves over a 4-bet must be
    able to move their whole stack in. The UI expresses the shove as a total
    bet on the street (stack + street bet); the conversion to the engine's
    raise increment must subtract both the street bet and the amount to call.
    """
    hh = HandHistory([Decimal(200)] * 6, small_blind=Decimal(1), big_blind=Decimal(2))
    hh.post_blinds_and_antes()
    hh.add_action(ActionType.FOLD)  # LJ
    hh.add_action(ActionType.RAISE, Decimal(3))  # HJ opens to 5
    hh.add_action(ActionType.RAISE, Decimal(13))  # CO 3-bets to 18
    hh.add_action(ActionType.RAISE, Decimal(22))  # BTN 4-bets to 40
    hh.add_action(ActionType.FOLD)  # SB
    hh.add_action(ActionType.FOLD)  # BB
    hh.add_action(ActionType.FOLD)  # HJ
    co = hh.current_player
    assert co.position == Position.CO
    total_on_street = co.stack + hh.current_player_street_bet()  # what the widget sends
    increment = (
        total_on_street
        - hh.current_player_street_bet()
        - hh.current_player_amount_to_call()
    )
    hh.add_action(ActionType.RAISE, increment)
    assert co.stack == 0
    assert co.street_bet(Street.PRE_FLOP) == Decimal(200)


def test_allin_preflop():
    hh = HandHistory.from_json((Path(__file__).parent / "allin_preflop.hh").read_text())
    assert hh.went_to_showdown
    assert hh.n_pseudo_actions() == 4
