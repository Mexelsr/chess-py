"""Complete chess rules engine.

Board representation
--------------------
A list of 64 characters. Index 0 is a1 and index 63 is h8.
White pieces are uppercase (PNBRQK), black pieces are lowercase.
Empty squares are ".".

The engine handles legal move generation, castling, en passant,
promotion, check / checkmate / stalemate, SAN notation, and draw rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

FILES = "abcdefgh"
RANKS = "12345678"

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

PROMOTION_PIECES = ("Q", "R", "B", "N")

PIECE_VALUES = {"p": 1, "n": 3, "b": 3, "r": 5, "q": 9, "k": 0}

KNIGHT_OFFSETS = ((1, 2), (2, 1), (-1, 2), (-2, 1),
                  (1, -2), (2, -1), (-1, -2), (-2, -1))
KING_OFFSETS = ((1, 0), (-1, 0), (0, 1), (0, -1),
                (1, 1), (1, -1), (-1, 1), (-1, -1))

# (rank delta, file delta, pieces that slide along this ray)
SLIDING_RAYS = (
    (1, 0, "rq"), (-1, 0, "rq"), (0, 1, "rq"), (0, -1, "rq"),
    (1, 1, "bq"), (1, -1, "bq"), (-1, 1, "bq"), (-1, -1, "bq"),
)


def other(color: str) -> str:
    return "b" if color == "w" else "w"


def color_of(piece: str) -> str:
    return "w" if piece.isupper() else "b"


def square_name(square: int) -> str:
    return FILES[square % 8] + RANKS[square // 8]


def square_index(name: str) -> int:
    return (ord(name[1]) - ord("1")) * 8 + (ord(name[0]) - ord("a"))


@dataclass(frozen=True)
class Move:
    """A single move. `flag` is 'castle', 'ep' (en passant) or 'double'."""

    frm: int
    to: int
    promo: Optional[str] = None
    flag: Optional[str] = None

    @property
    def uci(self) -> str:
        text = square_name(self.frm) + square_name(self.to)
        return text + (self.promo.lower() if self.promo else "")

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.uci


class Position:
    """A complete, immutable-by-convention chess position."""

    __slots__ = ("board", "turn", "castling", "ep", "halfmove", "fullmove")

    def __init__(self, board, turn="w", castling=frozenset(),
                 ep=None, halfmove=0, fullmove=1):
        self.board = board
        self.turn = turn
        self.castling = frozenset(castling)
        self.ep = ep
        self.halfmove = halfmove
        self.fullmove = fullmove

    # ------------------------------------------------------------------ setup

    @classmethod
    def start(cls) -> "Position":
        return cls.from_fen(START_FEN)

    @classmethod
    def from_fen(cls, fen: str) -> "Position":
        parts = fen.split()
        board = ["."] * 64
        for row_index, row in enumerate(parts[0].split("/")):
            rank = 7 - row_index
            file = 0
            for char in row:
                if char.isdigit():
                    file += int(char)
                else:
                    board[rank * 8 + file] = char
                    file += 1
        turn = parts[1] if len(parts) > 1 else "w"
        castling = frozenset(parts[2].replace("-", "")) if len(parts) > 2 else frozenset()
        ep = square_index(parts[3]) if len(parts) > 3 and parts[3] != "-" else None
        halfmove = int(parts[4]) if len(parts) > 4 else 0
        fullmove = int(parts[5]) if len(parts) > 5 else 1
        return cls(board, turn, castling, ep, halfmove, fullmove)

    def copy(self) -> "Position":
        return Position(list(self.board), self.turn, self.castling,
                        self.ep, self.halfmove, self.fullmove)

    def fen(self) -> str:
        rows = []
        for rank in range(7, -1, -1):
            empty = 0
            row = ""
            for file in range(8):
                piece = self.board[rank * 8 + file]
                if piece == ".":
                    empty += 1
                else:
                    if empty:
                        row += str(empty)
                        empty = 0
                    row += piece
            if empty:
                row += str(empty)
            rows.append(row)
        rights = "".join(sorted(self.castling)) or "-"
        ep = square_name(self.ep) if self.ep is not None else "-"
        return f"{'/'.join(rows)} {self.turn} {rights} {ep} {self.halfmove} {self.fullmove}"

    def key(self) -> str:
        """Position identity used for threefold-repetition detection."""
        return f"{''.join(self.board)}|{self.turn}|{''.join(sorted(self.castling))}|{self.ep}"

    # -------------------------------------------------------------- queries

    def king_square(self, color: str) -> int:
        try:
            return self.board.index("K" if color == "w" else "k")
        except ValueError:
            return -1

    def is_in_check(self, color: str) -> bool:
        king = self.king_square(color)
        return king != -1 and self.is_square_attacked(king, other(color))

    def is_square_attacked(self, square: int, by_color: str) -> bool:
        board = self.board
        file, rank = square % 8, square // 8

        # Pawns
        pawn = "P" if by_color == "w" else "p"
        pawn_dir = -8 if by_color == "w" else 8
        for file_delta in (-1, 1):
            if 0 <= file + file_delta < 8:
                source = square + pawn_dir + file_delta
                if 0 <= source < 64 and board[source] == pawn:
                    return True

        # Knights
        knight = "N" if by_color == "w" else "n"
        for rank_delta, file_delta in KNIGHT_OFFSETS:
            r, f = rank + rank_delta, file + file_delta
            if 0 <= r < 8 and 0 <= f < 8 and board[r * 8 + f] == knight:
                return True

        # King
        king = "K" if by_color == "w" else "k"
        for rank_delta, file_delta in KING_OFFSETS:
            r, f = rank + rank_delta, file + file_delta
            if 0 <= r < 8 and 0 <= f < 8 and board[r * 8 + f] == king:
                return True

        # Sliding pieces
        for rank_delta, file_delta, attackers in SLIDING_RAYS:
            r, f = rank + rank_delta, file + file_delta
            while 0 <= r < 8 and 0 <= f < 8:
                piece = board[r * 8 + f]
                if piece != ".":
                    if color_of(piece) == by_color and piece.lower() in attackers:
                        return True
                    break
                r += rank_delta
                f += file_delta

        return False

    # ------------------------------------------------------- move generation

    def generate_moves(self, legal: bool = True) -> list[Move]:
        """Return all moves for the side to move."""
        moves: list[Move] = []
        board = self.board
        turn = self.turn

        for square, piece in enumerate(board):
            if piece == "." or color_of(piece) != turn:
                continue
            kind = piece.lower()
            if kind == "p":
                self._generate_pawn_moves(square, piece, moves)
            elif kind == "n":
                self._generate_jump_moves(square, piece, moves, KNIGHT_OFFSETS)
            elif kind == "k":
                self._generate_jump_moves(square, piece, moves, KING_OFFSETS)
                self._generate_castle_moves(square, piece, moves)
            else:
                self._generate_sliding_moves(square, piece, moves)

        if not legal:
            return moves

        legal_moves = []
        for move in moves:
            if not self.make_move(move).is_in_check(turn):
                legal_moves.append(move)
        return legal_moves

    def _generate_pawn_moves(self, square: int, piece: str, moves: list[Move]) -> None:
        board = self.board
        rank, file = divmod(square, 8)
        white = piece == "P"
        step = 8 if white else -8
        start_rank = 1 if white else 6
        last_rank = 7 if white else 0

        def add(target: int) -> None:
            if target // 8 == last_rank:
                for promo in PROMOTION_PIECES:
                    moves.append(Move(square, target, promo))
            else:
                moves.append(Move(square, target))

        one = square + step
        if 0 <= one < 64 and board[one] == ".":
            add(one)
            two = square + 2 * step
            if rank == start_rank and 0 <= two < 64 and board[two] == ".":
                moves.append(Move(square, two, flag="double"))

        for file_delta in (-1, 1):
            if not 0 <= file + file_delta < 8:
                continue
            target = square + step + file_delta
            if not 0 <= target < 64:
                continue
            occupant = board[target]
            if occupant != "." and color_of(occupant) != color_of(piece):
                add(target)
            elif self.ep is not None and target == self.ep:
                moves.append(Move(square, target, flag="ep"))

    def _generate_jump_moves(self, square: int, piece: str,
                             moves: list[Move], offsets) -> None:
        board = self.board
        rank, file = divmod(square, 8)
        for rank_delta, file_delta in offsets:
            r, f = rank + rank_delta, file + file_delta
            if not (0 <= r < 8 and 0 <= f < 8):
                continue
            target = r * 8 + f
            occupant = board[target]
            if occupant == "." or color_of(occupant) != color_of(piece):
                moves.append(Move(square, target))

    def _generate_sliding_moves(self, square: int, piece: str,
                                moves: list[Move]) -> None:
        board = self.board
        rank, file = divmod(square, 8)
        kind = piece.lower()
        for rank_delta, file_delta, sliders in SLIDING_RAYS:
            if kind not in sliders:
                continue
            r, f = rank + rank_delta, file + file_delta
            while 0 <= r < 8 and 0 <= f < 8:
                target = r * 8 + f
                occupant = board[target]
                if occupant == ".":
                    moves.append(Move(square, target))
                else:
                    if color_of(occupant) != color_of(piece):
                        moves.append(Move(square, target))
                    break
                r += rank_delta
                f += file_delta

    def _generate_castle_moves(self, square: int, piece: str,
                               moves: list[Move]) -> None:
        board = self.board
        white = piece == "K"
        enemy = "b" if white else "w"
        rights = self.castling

        if white and square == 4:
            if ("K" in rights and board[7] == "R"
                    and board[5] == "." and board[6] == "."
                    and not any(self.is_square_attacked(s, enemy) for s in (4, 5, 6))):
                moves.append(Move(4, 6, flag="castle"))
            if ("Q" in rights and board[0] == "R"
                    and board[1] == "." and board[2] == "." and board[3] == "."
                    and not any(self.is_square_attacked(s, enemy) for s in (4, 3, 2))):
                moves.append(Move(4, 2, flag="castle"))
        elif not white and square == 60:
            if ("k" in rights and board[63] == "r"
                    and board[61] == "." and board[62] == "."
                    and not any(self.is_square_attacked(s, enemy) for s in (60, 61, 62))):
                moves.append(Move(60, 62, flag="castle"))
            if ("q" in rights and board[56] == "r"
                    and board[57] == "." and board[58] == "." and board[59] == "."
                    and not any(self.is_square_attacked(s, enemy) for s in (60, 59, 58))):
                moves.append(Move(60, 58, flag="castle"))

    # ---------------------------------------------------------- making moves

    def make_move(self, move: Move) -> "Position":
        """Return a new position after `move` (does not validate legality)."""
        position = self.copy()
        board = position.board
        piece = board[move.frm]
        color = color_of(piece)
        captured = board[move.to] != "." or move.flag == "ep"

        board[move.frm] = "."

        if move.flag == "ep":
            captured_square = move.to - 8 if color == "w" else move.to + 8
            board[captured_square] = "."

        if move.flag == "castle":
            if move.to > move.frm:           # king side
                rook_from, rook_to = move.frm + 3, move.frm + 1
            else:                             # queen side
                rook_from, rook_to = move.frm - 4, move.frm - 1
            board[rook_to] = board[rook_from]
            board[rook_from] = "."

        if move.promo:
            placed = move.promo.upper()
            if color == "b":
                placed = placed.lower()
        else:
            placed = piece
        board[move.to] = placed

        rights = set(position.castling)
        if piece == "K":
            rights -= {"K", "Q"}
        elif piece == "k":
            rights -= {"k", "q"}
        if move.frm == 0 or move.to == 0:
            rights.discard("Q")
        if move.frm == 7 or move.to == 7:
            rights.discard("K")
        if move.frm == 56 or move.to == 56:
            rights.discard("q")
        if move.frm == 63 or move.to == 63:
            rights.discard("k")
        position.castling = frozenset(rights)

        position.ep = (move.frm + move.to) // 2 if move.flag == "double" else None
        position.halfmove = 0 if (piece.lower() == "p" or captured) else self.halfmove + 1
        position.turn = other(self.turn)
        position.fullmove = self.fullmove + (1 if self.turn == "b" else 0)
        return position

    # ------------------------------------------------------------- notation

    def san(self, move: Move) -> str:
        """Standard algebraic notation for a legal move in this position."""
        piece = self.board[move.frm]
        legal = self.generate_moves()

        if move.flag == "castle":
            text = "O-O" if move.to > move.frm else "O-O-O"
        elif piece.lower() == "p":
            captures = self.board[move.to] != "." or move.flag == "ep"
            text = (FILES[move.frm % 8] + "x" if captures else "") + square_name(move.to)
            if move.promo:
                text += "=" + move.promo.upper()
        else:
            rivals = [
                candidate for candidate in legal
                if candidate.to == move.to
                and candidate.frm != move.frm
                and candidate.promo == move.promo
                and self.board[candidate.frm] == piece
            ]
            disambiguation = ""
            if rivals:
                same_file = any(m.frm % 8 == move.frm % 8 for m in rivals)
                same_rank = any(m.frm // 8 == move.frm // 8 for m in rivals)
                if not same_file:
                    disambiguation = FILES[move.frm % 8]
                elif not same_rank:
                    disambiguation = RANKS[move.frm // 8]
                else:
                    disambiguation = square_name(move.frm)
            captures = self.board[move.to] != "."
            text = (piece.upper() + disambiguation
                    + ("x" if captures else "") + square_name(move.to))

        after = self.make_move(move)
        if after.is_in_check(after.turn):
            text += "#" if not after.generate_moves() else "+"
        return text

    # ---------------------------------------------------------- game status

    def is_checkmate(self) -> bool:
        return self.is_in_check(self.turn) and not self.generate_moves()

    def is_stalemate(self) -> bool:
        return not self.is_in_check(self.turn) and not self.generate_moves()

    def is_insufficient_material(self) -> bool:
        """True when no checkmate is possible by any sequence of legal moves."""
        pieces = [
            (square, piece) for square, piece in enumerate(self.board)
            if piece != "." and piece.lower() != "k"
        ]
        if not pieces:
            return True
        if len(pieces) == 1 and pieces[0][1].lower() in "nb":
            return True
        if all(piece.lower() == "b" for _, piece in pieces):
            square_colors = {(square // 8 + square % 8) % 2 for square, _ in pieces}
            if len(square_colors) == 1:
                return True
        return False


class Game:
    """A game: position plus history, move notation, and result detection."""

    def __init__(self) -> None:
        self.position = Position.start()
        self.history: list[tuple[Position, Move, str]] = []
        self.result: Optional[str] = None
        self.result_reason = ""
        self._keys = [self.position.key()]

    @property
    def turn(self) -> str:
        return self.position.turn

    def legal_moves(self) -> list[Move]:
        return self.position.generate_moves()

    @property
    def last_move(self) -> Optional[Move]:
        return self.history[-1][1] if self.history else None

    def push(self, move: Move) -> str:
        """Play a legal move and return its SAN. Returns '' if illegal."""
        if move not in self.position.generate_moves():
            return ""
        san = self.position.san(move)
        self.history.append((self.position.copy(), move, san))
        self.position = self.position.make_move(move)
        self._keys.append(self.position.key())
        self._update_result()
        return san

    def undo(self) -> bool:
        if not self.history:
            return False
        self.position = self.history.pop()[0]
        self._keys.pop()
        self.result = None
        self.result_reason = ""
        return True

    def _update_result(self) -> None:
        position = self.position
        moves = position.generate_moves()

        if not moves:
            if position.is_in_check(position.turn):
                self.result = "0-1" if position.turn == "w" else "1-0"
                self.result_reason = "Checkmate"
            else:
                self.result = "1/2-1/2"
                self.result_reason = "Stalemate"
            return

        if position.halfmove >= 100:
            self.result = "1/2-1/2"
            self.result_reason = "Fifty-move rule"
        elif self._keys.count(self._keys[-1]) >= 3:
            self.result = "1/2-1/2"
            self.result_reason = "Threefold repetition"
        elif position.is_insufficient_material():
            self.result = "1/2-1/2"
            self.result_reason = "Insufficient material"
