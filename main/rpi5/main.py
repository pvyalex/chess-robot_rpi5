import cv2
import chess
import chess.engine
import os
from chess_robot_ik_only import ChessRobot, ServoName
from misc import white_Square, calibrate, warp_with, find_legal_move
from capture_image import GenerarePoze, GenerarePozaAutomata
from image_processing import MoveDetector

# --- CONFIGURARE RUTE ---
STOCKFISH_PATH = r"yolo26n\model\best-seg.pt"
robot = ChessRobot(port="COM3")

def main() -> None:
    board = chess.Board()
    engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
    engine.configure({"Skill Level": 1})
    detector = MoveDetector()

    print("=== START JOC ===")
    print("Așează piesele și pregătește-te de prima mutare.")

    # Calibrate once on the reference image — reuse M for all after-images
    GenerarePoze("Prima_Mutare.jpg")
    result = calibrate("Prima_Mutare.jpg")
    if result is None:
        print("Eroare la prima poza. Restarteaza.")
        engine.quit()
        return

    proc_ref, M, w, h = result
    detector.set_reference(proc_ref)

    try:
        while True:
            print("\nFa o mutare si apasa SPACE (sau ESC pentru iesire)...")
            GenerarePoze("A_Doua_Mutare.jpg")

            if not os.path.exists("A_Doua_Mutare.jpg"):
                print("Joc oprit de utilizator (ESC).")
                break

            # Use the SAME M from the reference image — no YOLO on after-image
            proc2 = warp_with("A_Doua_Mutare.jpg", M, w, h)
            if proc2 is None:
                continue

            pair, info = detector.detect(proc2)

            print(f"  [debug] top squares: {[x['square'] for x in info['ranked'][:4]]}")
            print(f"  [debug] confidence: {info['confidence']:.2f}  reliable: {info['reliable']}")

            move_obj = None

            # Primary path
            if pair is not None and info["reliable"]:
                sqA, sqB = pair
                move_pair = white_Square(sqA, sqB, board)
                candidate = chess.Move.from_uci("".join(move_pair))
                if candidate in board.legal_moves:
                    move_obj = candidate
                else:
                    print(f"  Top pair {move_pair} ilegal, caut in candidati...")

            # Fallback: search ranked list for any legal combination
            if move_obj is None:
                move_obj = find_legal_move(info["ranked"], board)

            if move_obj is None:
                print("Nicio mutare legala gasita in candidati. Refaci poza.")
                continue

            board.push(move_obj)
            print(f"Ai mutat: {move_obj.uci()}")

            if board.is_game_over():
                print("Jocul s-a terminat!")
                break

            result_sf = engine.play(board, chess.engine.Limit(time=0.8))
            ai_move = result_sf.move
            destination_square = board.piece_at(ai_move.to_square)
            board.push(ai_move)
            print(f"Mutarea Stockfish: {ai_move.uci()}")
            if destination_square is not None:
                print(f"Captura detectata pe {ai_move.uci()[2:]}")
                robot.take_piece_and_move(ai_move.uci()[:2], ai_move.uci()[2:])
            else:
                robot.move_piece_between_squares(ai_move.uci()[:2], ai_move.uci()[2:])
            if board.is_game_over():
                print("Jocul s-a terminat!, ai pierdut contra unui robot slab :(")
                break
            # New reference after Stockfish's move — recalibrate with YOLO
            # so M stays accurate for the new board state
            GenerarePozaAutomata("Prima_Mutare.jpg", delay=2)
            new_result = calibrate("Prima_Mutare.jpg")
            if new_result is not None:
                proc_ref, M, w, h = new_result
                detector.set_reference(proc_ref)
            else:
                print("Avertisment: recalibrare esuata, refolosim M anterior.")

            if os.path.exists("A_Doua_Mutare.jpg"):
                os.remove("A_Doua_Mutare.jpg")

    finally:
        engine.quit()
        print("Motorul de șah a fost închis.")


if __name__ == "__main__":
    main()