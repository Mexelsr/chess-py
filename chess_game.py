"""A desktop chess game built with Tkinter.

Run with:  python chess_game.py

Play locally with two players or against the built-in computer.
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import font as tkfont

import chess_ai
from chess_engine import Game, Move, color_of

if os.name == "nt":
    try:  # sharp text on high-DPI Windows displays
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

# ------------------------------------------------------------------ palette

BG = "#23211f"
PANEL = "#2e2b28"
PANEL_SOFT = "#383430"
TEXT = "#f0ece6"
MUTED = "#a8a199"
ACCENT = "#81b64c"
ACCENT_HOVER = "#95c95f"
BUTTON = "#3c3833"
BUTTON_HOVER = "#4a453f"
BOARD_LIGHT = "#eeeed2"
BOARD_DARK = "#769656"
HIGHLIGHT_LAST = "#f5f27a"
HIGHLIGHT_SELECTED = "#f3d859"
HIGHLIGHT_CHECK = "#e57373"
LEGAL_DOT = "#20351b"
WIN_TEXT = "#a9d86e"

UI_FONT = "Segoe UI"
FALLBACK_FONTS = ("Segoe UI Symbol", "DejaVu Sans", "Arial Unicode MS", "Arial")

GLYPHS = {
    "k": "\u265a",  # ♚
    "q": "\u265b",  # ♛
    "r": "\u265c",  # ♜
    "b": "\u265d",  # ♝
    "n": "\u265e",  # ♞
    "p": "\u265f",  # ♟
}

RESULT_TEXT = {
    "1-0": "White wins",
    "0-1": "Black wins",
    "1/2-1/2": "Draw",
}


class ChessApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.game = Game()
        self.mode = "human"          # "human" or "computer"
        self.flipped = False
        self.selected: int | None = None
        self.selected_moves: list[Move] = []
        self.thinking = False
        self.token = 0               # cancels stale computer searches
        self.square = 0.0
        self.board_x = 0.0
        self.board_y = 0.0
        self._ai_results: queue.Queue = queue.Queue()

        root.title("Chess")
        root.configure(bg=BG)
        width, height = 1080, 760
        screen_w, screen_h = root.winfo_screenwidth(), root.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2 - 20)
        root.geometry(f"{width}x{height}+{x}+{y}")
        root.minsize(940, 640)

        installed = set(tkfont.families(root))
        self.piece_font = next(
            (name for name in FALLBACK_FONTS if name in installed), "TkDefaultFont"
        )

        self._build_ui()
        self._refresh()

        root.bind("<Control-z>", lambda _event: self.undo())
        root.bind("<Control-n>", lambda _event: self.new_game())

        # Worker threads deliver their move here; the UI thread polls the queue.
        root.after(50, self._process_ai_results)

    # ------------------------------------------------------------------- UI

    def _build_ui(self) -> None:
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill="both", expand=True, padx=16, pady=16)

        board_frame = tk.Frame(main, bg=BG)
        board_frame.pack(side="left", fill="both", expand=True)

        self.canvas = tk.Canvas(
            board_frame, bg=BG, highlightthickness=0, cursor="hand2"
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Configure>", lambda _event: self._draw())

        panel = tk.Frame(main, bg=PANEL, width=300)
        panel.pack(side="right", fill="y", padx=(16, 0))
        panel.pack_propagate(False)

        tk.Label(
            panel, text="CHESS", font=(UI_FONT, 22, "bold"),
            bg=PANEL, fg=TEXT, anchor="w",
        ).pack(fill="x", padx=20, pady=(20, 0))
        tk.Label(
            panel, text="Full rules \u00b7 two players or the computer",
            font=(UI_FONT, 9), bg=PANEL, fg=MUTED, anchor="w",
        ).pack(fill="x", padx=20, pady=(2, 14))

        modes = tk.Frame(panel, bg=PANEL)
        modes.pack(fill="x", padx=16)
        self.mode_var = tk.StringVar(value="human")
        mode_options = (("human", "2 Players"), ("computer", "vs Computer"))
        for index, (value, label) in enumerate(mode_options):
            tk.Radiobutton(
                modes, text=label, value=value, variable=self.mode_var,
                command=self._mode_changed, indicatoron=False,
                font=(UI_FONT, 10, "bold"), bg=BUTTON, fg=TEXT,
                selectcolor=ACCENT, activebackground=BUTTON_HOVER,
                activeforeground=TEXT, bd=0, relief="flat", offrelief="flat",
                highlightthickness=0, padx=8, pady=7, cursor="hand2",
            ).pack(side="left", fill="x", expand=True,
                   padx=(0, 4) if index == 0 else (4, 0))

        card = tk.Frame(panel, bg=PANEL_SOFT)
        card.pack(fill="x", padx=16, pady=(14, 12))
        row = tk.Frame(card, bg=PANEL_SOFT)
        row.pack(fill="x", padx=14, pady=12)
        self.dot = tk.Canvas(
            row, width=18, height=18, bg=PANEL_SOFT, highlightthickness=0
        )
        self.dot.pack(side="left", anchor="n", pady=2, padx=(0, 10))
        self.dot_id = self.dot.create_oval(
            3, 3, 15, 15, fill="#f5f5f2", outline="#8a857d"
        )
        status_column = tk.Frame(row, bg=PANEL_SOFT)
        status_column.pack(side="left", fill="x", expand=True)
        self.status_label = tk.Label(
            status_column, text="White to move", font=(UI_FONT, 12, "bold"),
            bg=PANEL_SOFT, fg=TEXT, anchor="w",
        )
        self.status_label.pack(fill="x")
        self.detail_label = tk.Label(
            status_column, text="Move 1", font=(UI_FONT, 9),
            bg=PANEL_SOFT, fg=MUTED, anchor="w",
        )
        self.detail_label.pack(fill="x")

        moves_header = tk.Frame(panel, bg=PANEL)
        moves_header.pack(fill="x", padx=20, pady=(4, 6))
        tk.Label(
            moves_header, text="MOVES", font=(UI_FONT, 9, "bold"),
            bg=PANEL, fg=MUTED,
        ).pack(side="left")
        self.move_count_label = tk.Label(
            moves_header, text="0", font=(UI_FONT, 9), bg=PANEL, fg=MUTED
        )
        self.move_count_label.pack(side="right")

        list_frame = tk.Frame(panel, bg=PANEL)
        list_frame.pack(fill="both", expand=True, padx=16)
        scrollbar = tk.Scrollbar(
            list_frame, orient="vertical", bg=PANEL, troughcolor=PANEL_SOFT,
            activebackground=BUTTON_HOVER, bd=0, highlightthickness=0, width=10,
        )
        self.moves_list = tk.Listbox(
            list_frame, bg=PANEL_SOFT, fg=TEXT, bd=0, highlightthickness=0,
            font=("Consolas", 11), selectbackground="#4b5b3c",
            selectforeground=TEXT, activestyle="none", exportselection=False,
        )
        scrollbar.config(command=self.moves_list.yview)
        self.moves_list.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.moves_list.pack(side="left", fill="both", expand=True)

        buttons = tk.Frame(panel, bg=PANEL)
        buttons.pack(fill="x", padx=16, pady=(12, 8))

        new_button = tk.Button(
            buttons, text="New game", font=(UI_FONT, 11, "bold"),
            bg=ACCENT, fg="#1d2415", activebackground=ACCENT_HOVER,
            activeforeground="#1d2415", relief="flat", bd=0, pady=8,
            cursor="hand2", command=self.new_game,
        )
        new_button.pack(fill="x", pady=(0, 8))
        self._add_hover(new_button, ACCENT, ACCENT_HOVER)

        small_row = tk.Frame(buttons, bg=PANEL)
        small_row.pack(fill="x")
        undo_button = tk.Button(
            small_row, text="Undo", font=(UI_FONT, 10, "bold"),
            bg=BUTTON, fg=TEXT, activebackground=BUTTON_HOVER,
            activeforeground=TEXT, relief="flat", bd=0, pady=7,
            cursor="hand2", command=self.undo,
        )
        flip_button = tk.Button(
            small_row, text="Flip board", font=(UI_FONT, 10, "bold"),
            bg=BUTTON, fg=TEXT, activebackground=BUTTON_HOVER,
            activeforeground=TEXT, relief="flat", bd=0, pady=7,
            cursor="hand2", command=self.flip,
        )
        undo_button.pack(side="left", fill="x", expand=True, padx=(0, 4))
        flip_button.pack(side="right", fill="x", expand=True, padx=(4, 0))
        self._add_hover(undo_button, BUTTON, BUTTON_HOVER)
        self._add_hover(flip_button, BUTTON, BUTTON_HOVER)

        tk.Label(
            panel,
            text="Click a piece, then a highlighted square.\n"
                 "Ctrl+Z undo  \u00b7  Ctrl+N new game",
            font=(UI_FONT, 8), bg=PANEL, fg=MUTED, justify="left",
        ).pack(fill="x", padx=20, pady=(0, 16))

    @staticmethod
    def _add_hover(widget: tk.Widget, normal: str, hover: str) -> None:
        widget.bind("<Enter>", lambda _event: widget.configure(bg=hover))
        widget.bind("<Leave>", lambda _event: widget.configure(bg=normal))

    # -------------------------------------------------------------- actions

    def new_game(self) -> None:
        self.token += 1
        self.thinking = False
        self.game = Game()
        self.selected = None
        self.selected_moves = []
        self._refresh()

    def flip(self) -> None:
        self.flipped = not self.flipped
        self._draw()

    def undo(self) -> None:
        if not self.game.history:
            return
        self.token += 1
        self.thinking = False
        self.game.undo()
        # Against the computer, rewind the whole turn so the human moves next.
        if (self.mode == "computer" and self.game.history
                and self.game.position.turn == "b"):
            self.game.undo()
        self.selected = None
        self.selected_moves = []
        self._refresh()

    def _mode_changed(self) -> None:
        self.mode = self.mode_var.get()
        self.token += 1
        self.thinking = False
        if (self.mode == "computer" and not self.game.result
                and self.game.position.turn == "b"):
            self._start_computer_turn()
        else:
            self._refresh()

    # ---------------------------------------------------------------- click

    def _on_click(self, event: tk.Event) -> None:
        if self.game.result or self.thinking:
            return
        if self.mode == "computer" and self.game.position.turn == "b":
            return

        square = self._square_at(event.x, event.y)
        if square is None:
            return

        position = self.game.position
        piece = position.board[square]

        if self.selected is not None:
            options = [move for move in self.selected_moves if move.to == square]
            if options:
                move = options[0]
                if move.promo:
                    choice = self._ask_promotion()
                    move = next(
                        (candidate for candidate in options
                         if candidate.promo == choice),
                        options[0],
                    )
                self._play(move)
                return

        if piece != "." and color_of(piece) == position.turn:
            if self.selected == square:
                self.selected = None
                self.selected_moves = []
            else:
                self.selected = square
                self.selected_moves = [
                    move for move in self.game.legal_moves()
                    if move.frm == square
                ]
        else:
            self.selected = None
            self.selected_moves = []

        self._draw()

    def _play(self, move: Move) -> None:
        if not self.game.push(move):
            return
        self.selected = None
        self.selected_moves = []
        self._refresh()
        self._maybe_computer_turn()

    def _ask_promotion(self) -> str:
        choice = {"piece": "Q"}
        dialog = tk.Toplevel(self.root)
        dialog.title("Promote pawn")
        dialog.configure(bg=PANEL, padx=14, pady=14)
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(
            dialog, text="Promote pawn to", font=(UI_FONT, 11, "bold"),
            bg=PANEL, fg=TEXT,
        ).pack(pady=(0, 10))

        row = tk.Frame(dialog, bg=PANEL)
        row.pack()

        def choose(piece: str) -> None:
            choice["piece"] = piece
            dialog.destroy()

        for piece in "QRBN":
            button = tk.Button(
                row, text=GLYPHS[piece.lower()],
                font=(self.piece_font, 26), width=2, bg=BUTTON, fg=TEXT,
                activebackground=ACCENT, activeforeground="#1d2415",
                relief="flat", bd=0, cursor="hand2",
                command=lambda p=piece: choose(p),
            )
            button.pack(side="left", padx=3)

        dialog.protocol("WM_DELETE_WINDOW", lambda: choose("Q"))
        dialog.update_idletasks()
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        x = root_x + (self.root.winfo_width() - dialog.winfo_reqwidth()) // 2
        y = root_y + (self.root.winfo_height() - dialog.winfo_reqheight()) // 3
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
        dialog.wait_window()
        return choice["piece"]

    # ------------------------------------------------------------ computer

    def _maybe_computer_turn(self) -> None:
        if (self.mode == "computer" and not self.game.result
                and self.game.position.turn == "b"):
            self._start_computer_turn()

    def _start_computer_turn(self) -> None:
        self.thinking = True
        self._refresh()
        token = self.token
        snapshot = self.game.position.copy()

        def think() -> None:
            try:
                move = chess_ai.best_move(snapshot, depth=3)
            except Exception:
                move = None
            self._ai_results.put((move, token))

        threading.Thread(target=think, daemon=True).start()

    def _process_ai_results(self) -> None:
        try:
            while True:
                move, token = self._ai_results.get_nowait()
                if token == self.token:
                    self._computer_finished(move, token)
                    break
        except queue.Empty:
            pass
        try:
            self.root.after(50, self._process_ai_results)
        except tk.TclError:
            pass

    def _computer_finished(self, move: Move | None, token: int) -> None:
        if token != self.token:
            return
        self.thinking = False
        if move is not None and not self.game.result:
            if move in self.game.legal_moves():
                self._play(move)
                return
        self._refresh()

    # --------------------------------------------------------------- display

    def _refresh(self) -> None:
        self._sync_status()
        self._sync_moves()
        self._draw()

    def _sync_status(self) -> None:
        position = self.game.position
        self.move_count_label.config(text=str((len(self.game.history) + 1) // 2))

        if self.game.result:
            self.status_label.config(
                text=RESULT_TEXT.get(self.game.result, "Game over"), fg=WIN_TEXT
            )
            self.detail_label.config(
                text=f"{self.game.result_reason}  \u00b7  {self.game.result}"
            )
            if self.game.result == "1-0":
                self.dot.itemconfigure(self.dot_id, fill="#f5f5f2")
            elif self.game.result == "0-1":
                self.dot.itemconfigure(self.dot_id, fill="#1b1b19")
            else:
                self.dot.itemconfigure(self.dot_id, fill="#8a857d")
            return

        self.status_label.config(fg=TEXT)
        if self.thinking:
            self.status_label.config(text="Computer is thinking\u2026")
            self.detail_label.config(
                text=f"Move {position.fullmove}  \u00b7  looking ahead"
            )
            self.dot.itemconfigure(
                self.dot_id, fill="#1b1b19" if position.turn == "b" else "#f5f5f2"
            )
            return

        side = "White" if position.turn == "w" else "Black"
        if position.is_in_check(position.turn):
            self.status_label.config(text=f"{side} is in check")
        else:
            self.status_label.config(text=f"{side} to move")
        detail = f"Move {position.fullmove}"
        if self.mode == "computer":
            detail += "  \u00b7  vs Computer"
        self.detail_label.config(text=detail)
        self.dot.itemconfigure(
            self.dot_id, fill="#f5f5f2" if position.turn == "w" else "#1b1b19"
        )

    def _sync_moves(self) -> None:
        self.moves_list.delete(0, "end")
        history = self.game.history
        for index in range(0, len(history), 2):
            number = index // 2 + 1
            white = history[index][2]
            black = history[index + 1][2] if index + 1 < len(history) else ""
            self.moves_list.insert("end", f"{number:>3}.  {white:<7} {black}")
        if history:
            self.moves_list.yview_moveto(1.0)

    # --------------------------------------------------------------- drawing

    def _to_screen(self, square: int) -> tuple[int, int]:
        rank, file = divmod(square, 8)
        if self.flipped:
            return rank, 7 - file
        return 7 - rank, file

    def _from_screen(self, screen_rank: int, screen_file: int) -> int:
        if self.flipped:
            return screen_rank * 8 + (7 - screen_file)
        return (7 - screen_rank) * 8 + screen_file

    def _square_at(self, x: float, y: float) -> int | None:
        if self.square <= 0:
            return None
        file = int((x - self.board_x) // self.square)
        rank = int((y - self.board_y) // self.square)
        if 0 <= file < 8 and 0 <= rank < 8:
            return self._from_screen(rank, file)
        return None

    def _draw(self) -> None:
        canvas = self.canvas
        canvas.delete("all")

        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width < 60 or height < 60:
            return

        side = min(width, height)
        margin = side * 0.05
        board_size = side - 2 * margin
        self.square = board_size / 8
        self.board_x = (width - board_size) / 2
        self.board_y = (height - board_size) / 2
        square = self.square
        origin_x, origin_y = self.board_x, self.board_y

        position = self.game.position
        last_move = self.game.last_move
        checked_king = None
        if position.is_in_check(position.turn):
            checked_king = position.king_square(position.turn)

        for target in range(64):
            screen_rank, screen_file = self._to_screen(target)
            x1 = origin_x + screen_file * square
            y1 = origin_y + screen_rank * square
            rank, file = divmod(target, 8)
            color = BOARD_LIGHT if (rank + file) % 2 else BOARD_DARK
            canvas.create_rectangle(x1, y1, x1 + square, y1 + square,
                                    fill=color, outline="")

            if last_move is not None and target in (last_move.frm, last_move.to):
                canvas.create_rectangle(x1, y1, x1 + square, y1 + square,
                                        fill=HIGHLIGHT_LAST, outline="")
            if checked_king == target:
                canvas.create_rectangle(x1, y1, x1 + square, y1 + square,
                                        fill=HIGHLIGHT_CHECK, outline="")
            if self.selected == target:
                canvas.create_rectangle(x1, y1, x1 + square, y1 + square,
                                        fill=HIGHLIGHT_SELECTED, outline="")

        piece_size = max(10, int(square * 0.80))
        piece_font = (self.piece_font, piece_size)
        shadow = max(1.0, square * 0.025)

        for target, piece in enumerate(position.board):
            if piece == ".":
                continue
            screen_rank, screen_file = self._to_screen(target)
            center_x = origin_x + (screen_file + 0.5) * square
            center_y = origin_y + (screen_rank + 0.5) * square
            glyph = GLYPHS[piece.lower()]
            if piece.isupper():
                canvas.create_text(
                    center_x + shadow, center_y + shadow, text=glyph,
                    font=piece_font, fill="#4a4a44", anchor="center",
                )
                canvas.create_text(
                    center_x, center_y, text=glyph,
                    font=piece_font, fill="#f7f7f2", anchor="center",
                )
            else:
                canvas.create_text(
                    center_x, center_y, text=glyph,
                    font=piece_font, fill="#1d1d1b", anchor="center",
                )

        for move in self.selected_moves:
            screen_rank, screen_file = self._to_screen(move.to)
            center_x = origin_x + (screen_file + 0.5) * square
            center_y = origin_y + (screen_rank + 0.5) * square
            occupied = (position.board[move.to] != "."
                        or move.flag == "ep")
            if occupied:
                radius = square * 0.43
                canvas.create_oval(
                    center_x - radius, center_y - radius,
                    center_x + radius, center_y + radius,
                    outline=LEGAL_DOT, width=max(2, int(square * 0.055)),
                )
            else:
                radius = square * 0.135
                canvas.create_oval(
                    center_x - radius, center_y - radius,
                    center_x + radius, center_y + radius,
                    fill=LEGAL_DOT, outline="",
                )

        coord_font = (UI_FONT, max(8, int(square * 0.16)))
        for screen_file in range(8):
            label = chr(ord("a") + screen_file) if not self.flipped \
                else chr(ord("h") - screen_file)
            canvas.create_text(
                origin_x + (screen_file + 0.5) * square,
                origin_y + board_size + margin * 0.5,
                text=label, font=coord_font, fill=MUTED, anchor="center",
            )
        for screen_rank in range(8):
            label = str(8 - screen_rank) if not self.flipped \
                else str(screen_rank + 1)
            canvas.create_text(
                origin_x - margin * 0.5,
                origin_y + (screen_rank + 0.5) * square,
                text=label, font=coord_font, fill=MUTED, anchor="center",
            )

        if self.game.result:
            self._draw_result_card(origin_x, origin_y, board_size, square)

    def _draw_result_card(self, origin_x: float, origin_y: float,
                          board_size: float, square: float) -> None:
        canvas = self.canvas
        card_width = board_size * 0.78
        card_height = square * 2.4
        center_x = origin_x + board_size / 2
        center_y = origin_y + board_size / 2
        x1 = center_x - card_width / 2
        x2 = center_x + card_width / 2
        y1 = center_y - card_height / 2
        y2 = center_y + card_height / 2

        canvas.create_rectangle(
            x1 + 5, y1 + 7, x2 + 5, y2 + 7,
            fill="#000000", stipple="gray50", outline="",
        )
        canvas.create_rectangle(
            x1, y1, x2, y2, fill="#211f1c", outline="#4b463e", width=2,
        )

        canvas.create_text(
            center_x, center_y - square * 0.38,
            text=self.game.result_reason or "Game over",
            font=(UI_FONT, max(12, int(square * 0.34)), "bold"),
            fill=TEXT, anchor="center",
        )
        canvas.create_text(
            center_x, center_y + square * 0.12,
            text=f"{RESULT_TEXT.get(self.game.result, '')}   "
                 f"{self.game.result or ''}".strip(),
            font=(UI_FONT, max(10, int(square * 0.20)), "bold"),
            fill=WIN_TEXT, anchor="center",
        )
        canvas.create_text(
            center_x, center_y + square * 0.62,
            text="Press New game to play again",
            font=(UI_FONT, max(8, int(square * 0.145))),
            fill=MUTED, anchor="center",
        )


def main() -> None:
    root = tk.Tk()
    ChessApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
