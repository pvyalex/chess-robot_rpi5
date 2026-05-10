from itertools import permutations

import chess
import cv2

from get_board import calibrate_board_from_image, warp_board

MODEL_PATH = r"C:\Users\alext\Desktop\ETCTI\VARF\varf_proj\chess_model_export\best-seg.pt"


def calibrate(path: str):
    img = cv2.imread(path)
    if img is None:
        print(f"Nu am putut citi imaginea: {path}")
        return None
    try:
        M, w, h = calibrate_board_from_image(img, MODEL_PATH, out_size=1024)
        warped = warp_board(img, M, w, h)
        return warped, M, w, h
    except Exception as e:
        print(f"Eroare la decuparea tablei cu YOLO: {e}")
        return None


def warp_with(path: str, M, w: int, h: int):
    img = cv2.imread(path)
    if img is None:
        print(f"Nu am putut citi imaginea: {path}")
        return None
    return warp_board(img, M, w, h)


def find_legal_move(ranked: list, board: chess.Board):
    squares = [r["square"] for r in ranked]
    for sq_a, sq_b in permutations(squares, 2):
        try:
            move = chess.Move.from_uci(sq_a + sq_b)
        except ValueError:
            continue
        if move in board.legal_moves:
            print(f"  [fallback] mutare legala gasita: {sq_a}{sq_b}")
            return move
    return None


def white_Square(move1, move2, board):
    sq1 = chess.parse_square(move1)
    sq2 = chess.parse_square(move2)

    piece1 = board.piece_at(sq1)
    piece2 = board.piece_at(sq2)

    if piece1 is not None and piece1.color == chess.WHITE:
        return (move1, move2)
    elif piece2 is not None and piece2.color == chess.WHITE:
        return (move2, move1)
    else:
        return (move1, move2)
