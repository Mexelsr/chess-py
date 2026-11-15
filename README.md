# Chess

A complete desktop chess game written in Python with Tkinter. No third-party
packages required.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)

## Run

```bash
python chess_game.py
```

Tkinter ships with the standard Windows and macOS Python installers. On Linux,
install it with your package manager if needed, for example:

```bash
sudo apt install python3-tk
```

## Play

- Click one of your pieces, then click a highlighted square to move.
- Dots show quiet moves; rings show captures.
- Pawns reaching the last rank open a promotion picker.
- **2 Players** is pass-and-play. **vs Computer** puts the built-in engine on
  the black side.
- **Undo** rewinds a move (against the computer it rewinds the whole turn).
- **Flip board** switches the view, and **New game** resets the board.

Keyboard: `Ctrl+Z` undo, `Ctrl+N` new game.

## Features

- Full legal move generation: pins, checks, castling, en passant, promotion
- Check, checkmate, stalemate, threefold repetition, fifty-move rule, and
  insufficient-material draws
- Standard algebraic notation (SAN) move list, including disambiguation and
  `+` / `#` suffixes
- Board coordinates, last-move and check highlighting, legal target markers
- Computer opponent: alpha-beta negamax with piece-square tables, running in a
  background thread so the window stays responsive
- Resizable board with a fixed side panel

## Files

| File | Purpose |
| --- | --- |
| `chess_game.py` | Tkinter interface and game controls |
| `chess_engine.py` | Board representation, rules, SAN, and game state |
| `chess_ai.py` | Computer opponent |

## Correctness

The move generator was checked against standard perft positions, including
the starting position (197,281 nodes at depth 4), Kiwipete (97,862 at depth 3),
and positions 3–5 from the Chess Programming Wiki perft suite. All counts
matched exactly.
