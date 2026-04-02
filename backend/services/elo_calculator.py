"""Elo rating math + persistence. Standard Elo with K=32, starting rating 1200."""
from backend.config import DEFAULT_ELO, ELO_K_FACTOR


def calculate_elo(
    rating_a: float,
    rating_b: float,
    winner: str,
    k: int = ELO_K_FACTOR,
) -> tuple[float, float]:
    """
    Calculate new Elo ratings after a match.

    Args:
        rating_a: Current Elo of model A.
        rating_b: Current Elo of model B.
        winner: 'a', 'b', or 'tie'.
        k: K-factor (default 32).

    Returns:
        (new_rating_a, new_rating_b)
    """
    expected_a = 1 / (1 + 10 ** ((rating_b - rating_a) / 400))
    expected_b = 1 - expected_a

    if winner == "a":
        score_a, score_b = 1.0, 0.0
    elif winner == "b":
        score_a, score_b = 0.0, 1.0
    else:  # tie
        score_a, score_b = 0.5, 0.5

    new_a = rating_a + k * (score_a - expected_a)
    new_b = rating_b + k * (score_b - expected_b)
    return round(new_a, 1), round(new_b, 1)
