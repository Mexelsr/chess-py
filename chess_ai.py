"""A compact computer opponent: alpha-beta negamax with simple evaluation.

Strong enough for casual play, small enough to read. Depth 3 means the
computer looks three plies ahead and orders captures first.
"""

from __future__ import annotations

import random

from chess_engine import PIECE_VALUES, Move, Position

MATE = 100_000.0
INF = float("inf")


def _table(rows: list[list[int]]) -> list[int]:
    """Convert a table written from rank 8 to rank 1 into a1..h8 order."""
    return [value for row in reversed(rows) for value in row]


PAWN_TABLE = _table([
    [0, 0, 0, 0, 0, 0, 0, 0],
    [50, 50, 50, 50, 50, 50, 50, 50],
    [10, 10, 20, 30, 30, 20, 10, 10],
    [5, 5, 10, 25, 25, 10, 5, 5],
    [0, 0, 0, 20, 20, 0, 0, 0],
    [5, -5, -10, 0, 0, -10, -5, 5],
    [5, 10, 10, -20, -20, 10, 10, 5],
    [0, 0, 0, 0, 0, 0, 0, 0],
])

KNIGHT_TABLE = _table([
    [-50, -40, -30, -30, -30, -30, -40, -50],
    [-40, -20, 0, 0, 0, 0, -20, -40],
    [-30, 0, 10, 15, 15, 10, 0, -30],
    [-30, 5, 15, 20, 20, 15, 5, -30],
    [-30, 0, 15, 20, 20, 15, 0, -30],
    [-30, 5, 10, 15, 15, 10, 5, -30],
    [-40, -20, 0, 5, 5, 0, -20, -40],
    [-50, -40, -30, -30, -30, -30, -40, -50],
])

BISHOP_TABLE = _table([
    [-20, -10, -10, -10, -10, -10, -10, -20],
    [-10, 0, 0, 0, 0, 0, 0, -10],
    [-10, 0, 5, 10, 10, 5, 0, -10],
    [-10, 5, 5, 10, 10, 5, 5, -10],
    [-10, 0, 10, 10, 10, 10, 0, -10],
    [-10, 10, 10, 10, 10, 10, 10, -10],
    [-10, 5, 0, 0, 0, 0, 5, -10],
    [-20, -10, -10, -10, -10, -10, -10, -20],
])

ROOK_TABLE = _table([
    [0, 0, 0, 0, 0, 0, 0, 0],
    [5, 10, 10, 10, 10, 10, 10, 5],
    [-5, 0, 0, 0, 0, 0, 0, -5],
    [-5, 0, 0, 0, 0, 0, 0, -5],
    [-5, 0, 0, 0, 0, 0, 0, -5],
    [-5, 0, 0, 0, 0, 0, 0, -5],
    [-5, 0, 0, 0, 0, 0, 0, -5],
    [0, 0, 0, 5, 5, 0, 0, 0],
])

QUEEN_TABLE = _table([
    [-20, -10, -10, -5, -5, -10, -10, -20],
    [-10, 0, 0, 0, 0, 0, 0, -10],
    [-10, 0, 5, 5, 5, 5, 0, -10],
    [-5, 0, 5, 5, 5, 5, 0, -5],
    [0, 0, 5, 5, 5, 5, 0, -5],
    [-10, 5, 5, 5, 5, 5, 0, -10],
    [-10, 0, 5, 0, 0, 0, 0, -10],
    [-20, -10, -10, -5, -5, -10, -10, -20],
])

KING_TABLE = _table([
    [-30, -40, -40, -50, -50, -40, -40, -30],
    [-30, -40, -40, -50, -50, -40, -40, -30],
    [-30, -40, -40, -50, -50, -40, -40, -30],
    [-30, -40, -40, -50, -50, -40, -40, -30],
    [-20, -30, -30, -40, -40, -30, -30, -20],
    [-10, -20, -20, -20, -20, -20, -20, -10],
    [20, 20, 0, 0, 0, 0, 20, 20],
    [20, 30, 10, 0, 0, 10, 30, 20],
])

PIECE_TABLES = {
    "p": PAWN_TABLE,
    "n": KNIGHT_TABLE,
    "b": BISHOP_TABLE,
    "r": ROOK_TABLE,
    "q": QUEEN_TABLE,
    "k": KING_TABLE,
}


def _evaluate(position: Position) -> float:
    """Static evaluation in pawns, positive for White."""
    score = 0.0
    white_bishops = 0
    black_bishops = 0

    for square, piece in enumerate(position.board):
        if piece == ".":
            continue
        kind = piece.lower()
        rank, file = divmod(square, 8)
        white = piece.isupper()

        table_square = square if white else (7 - rank) * 8 + file
        value = PIECE_VALUES[kind] + PIECE_TABLES[kind][table_square] / 100.0

        if kind == "b":
            if white:
                white_bishops += 1
            else:
                black_bishops += 1

        score += value if white else -value

    if white_bishops >= 2:
        score += 0.30
    if black_bishops >= 2:
        score -= 0.30

    return score


def _move_priority(position: Position, move: Move) -> float:
    """Order captures and promotions first to make alpha-beta effective."""
    victim = position.board[move.to]
    priority = 0.0
    if victim != ".":
        attacker = position.board[move.frm]
        priority += 10 * PIECE_VALUES[victim.lower()] - PIECE_VALUES[attacker.lower()]
    if move.promo:
        priority += PIECE_VALUES[move.promo.lower()]
    if move.flag == "ep":
        priority += 9
    if move.flag == "castle":
        priority += 1
    return priority


def _search(position: Position, depth: int, alpha: float, beta: float,
            ply: int) -> float:
    moves = position.generate_moves()

    if not moves:
        if position.is_in_check(position.turn):
            return -MATE + ply
        return 0.0

    if depth <= 0:
        white_score = _evaluate(position)
        return white_score if position.turn == "w" else -white_score

    moves.sort(key=lambda move: _move_priority(position, move), reverse=True)

    best = -INF
    for move in moves:
        score = -_search(position.make_move(move), depth - 1,
                         -beta, -alpha, ply + 1)
        if score > best:
            best = score
        if score > alpha:
            alpha = score
        if alpha >= beta:
            break
    return best


def best_move(position: Position, depth: int = 3) -> Move | None:
    """Pick the computer's move for the side to move."""
    moves = position.generate_moves()
    if not moves:
        return None

    # A little randomness between near-equal moves keeps games varied.
    moves.sort(
        key=lambda move: _move_priority(position, move) + random.random() * 0.01,
        reverse=True,
    )

    best = moves[0]
    best_score = -INF
    alpha, beta = -INF, INF

    for move in moves:
        score = -_search(position.make_move(move), depth - 1,
                         -beta, -alpha, 1)
        if score > best_score:
            best_score = score
            best = move
        if score > alpha:
            alpha = score

    return best
