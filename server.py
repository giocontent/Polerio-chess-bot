import pickle
import random
import time
import math
from pathlib import Path
from collections import Counter

import chess
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
BOOK_PATH = BASE_DIR / "polerio_move_book.pkl"

# Per non superare il timeout del frontend.
# Se il bot dovesse pensare troppo, abbassa a 2.5.
SEARCH_TIME_LIMIT = 3.2

# Profondità del mini-motore.
# 2 = veloce ma più debole
# 3 = più forte, circa stile rapid umano base/intermedio
MAX_SEARCH_DEPTH = 3

MATE_SCORE = 1_000_000

PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}


# ============================================================
# FASTAPI
# ============================================================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BotMoveRequest(BaseModel):
    fen: str


# ============================================================
# POLERIO BOOK
# ============================================================

def fen_key(board: chess.Board) -> str:
    """
    Usiamo solo:
    posizione, turno, arrocco, en passant.
    Così la chiave combacia col libro mosse.
    """
    return " ".join(board.fen().split()[:4])


def load_move_book():
    if not BOOK_PATH.exists():
        print("ATTENZIONE: polerio_move_book.pkl non trovato.")
        return {}

    with open(BOOK_PATH, "rb") as f:
        book = pickle.load(f)

    print(f"Repertorio Polerio caricato: {len(book)} posizioni.")
    return book


MOVE_BOOK = load_move_book()


def normalize_move_uci(move):
    if isinstance(move, chess.Move):
        return move.uci()
    return str(move)


def choose_from_book(board: chess.Board):
    """
    Se la posizione è nel repertorio, sceglie una mossa realmente presente nel libro.
    """
    key = fen_key(board)

    if key not in MOVE_BOOK:
        return None

    entry = MOVE_BOOK[key]
    legal_uci = {move.uci() for move in board.legal_moves}

    candidates = []

    if isinstance(entry, Counter) or isinstance(entry, dict):
        for move, weight in entry.items():
            move_uci = normalize_move_uci(move)

            if move_uci in legal_uci:
                try:
                    weight = int(weight)
                except Exception:
                    weight = 1

                candidates.append((move_uci, max(weight, 1)))

    elif isinstance(entry, list):
        for move in entry:
            move_uci = normalize_move_uci(move)

            if move_uci in legal_uci:
                candidates.append((move_uci, 1))

    if not candidates:
        return None

    moves = [x[0] for x in candidates]
    weights = [x[1] for x in candidates]

    chosen_uci = random.choices(moves, weights=weights, k=1)[0]
    return chess.Move.from_uci(chosen_uci)


# ============================================================
# MINI ENGINE 1300 RAPID STYLE
# ============================================================

class SearchTimeout(Exception):
    pass


def check_time(start_time):
    if time.perf_counter() - start_time > SEARCH_TIME_LIMIT:
        raise SearchTimeout()


def center_bonus(square: chess.Square) -> int:
    """
    Bonus per avvicinarsi al centro.
    """
    file = chess.square_file(square)
    rank = chess.square_rank(square)

    distance = abs(file - 3.5) + abs(rank - 3.5)
    return int(max(0, 28 - 7 * distance))


def piece_positional_bonus(piece: chess.Piece, square: chess.Square, fullmove_number: int) -> int:
    """
    Bonus posizionale semplice.
    Non è Stockfish, ma rende il bot molto meno casuale.
    """
    piece_type = piece.piece_type
    color = piece.color
    rank = chess.square_rank(square)
    file = chess.square_file(square)

    bonus = 0

    # Centro
    c_bonus = center_bonus(square)

    if piece_type == chess.KNIGHT:
        bonus += c_bonus * 3

        # Penalizza cavalli ai bordi
        if file in [0, 7] or rank in [0, 7]:
            bonus -= 35

    elif piece_type == chess.BISHOP:
        bonus += c_bonus * 2

    elif piece_type == chess.PAWN:
        # Pedoni centrali più importanti
        if file in [3, 4]:
            bonus += 18

        # Avanzamento pedoni
        if color == chess.WHITE:
            bonus += rank * 8
        else:
            bonus += (7 - rank) * 8

    elif piece_type == chess.ROOK:
        # Torri più utili su file centrali/semi-centrali
        if file in [2, 3, 4, 5]:
            bonus += 10

    elif piece_type == chess.QUEEN:
        bonus += c_bonus

        # Donna troppo attiva in apertura: leggermente penalizzata
        if fullmove_number <= 8:
            if color == chess.WHITE and square != chess.D1:
                bonus -= 25
            if color == chess.BLACK and square != chess.D8:
                bonus -= 25

    elif piece_type == chess.KING:
        # In apertura/middlegame: re arroccato = bene
        if fullmove_number <= 25:
            if color == chess.WHITE and square in [chess.G1, chess.C1]:
                bonus += 70
            elif color == chess.BLACK and square in [chess.G8, chess.C8]:
                bonus += 70

            # Re al centro dopo un po' = male
            if color == chess.WHITE and square == chess.E1 and fullmove_number >= 8:
                bonus -= 45
            if color == chess.BLACK and square == chess.E8 and fullmove_number >= 8:
                bonus -= 45

    return bonus


def development_score(board: chess.Board) -> int:
    """
    Bonus sviluppo in apertura.
    Positivo per il Bianco, negativo per il Nero.
    """
    score = 0

    # Pezzi minori bianchi sviluppati
    white_start_squares = [chess.B1, chess.G1, chess.C1, chess.F1]
    black_start_squares = [chess.B8, chess.G8, chess.C8, chess.F8]

    for sq in white_start_squares:
        piece = board.piece_at(sq)
        if piece and piece.color == chess.WHITE and piece.piece_type in [chess.KNIGHT, chess.BISHOP]:
            score -= 25

    for sq in black_start_squares:
        piece = board.piece_at(sq)
        if piece and piece.color == chess.BLACK and piece.piece_type in [chess.KNIGHT, chess.BISHOP]:
            score += 25

    return score


def material_and_position_score(board: chess.Board) -> int:
    """
    Valutazione dalla prospettiva del Bianco.
    Positivo = meglio il Bianco.
    Negativo = meglio il Nero.
    """
    score = 0

    for square, piece in board.piece_map().items():
        sign = 1 if piece.color == chess.WHITE else -1

        score += sign * PIECE_VALUES[piece.piece_type]
        score += sign * piece_positional_bonus(piece, square, board.fullmove_number)

    score += development_score(board)

    return score


def mobility_score(board: chess.Board) -> int:
    """
    Bonus leggero per mobilità.
    """
    temp = board.copy(stack=False)

    temp.turn = chess.WHITE
    white_mobility = len(list(temp.legal_moves))

    temp.turn = chess.BLACK
    black_mobility = len(list(temp.legal_moves))

    return 3 * (white_mobility - black_mobility)


def king_pressure_score(board: chess.Board) -> int:
    """
    Bonus se il lato ha iniziativa/scacco.
    """
    score = 0

    if board.is_check():
        # Se è il turno del Bianco ed è sotto scacco, bene per il Nero.
        # Se è il turno del Nero ed è sotto scacco, bene per il Bianco.
        score += -45 if board.turn == chess.WHITE else 45

    return score


def evaluate_board(board: chess.Board) -> int:
    """
    Valutazione completa.
    """
    if board.is_checkmate():
        return -MATE_SCORE if board.turn == chess.WHITE else MATE_SCORE

    if board.is_stalemate() or board.is_insufficient_material():
        return 0

    score = 0
    score += material_and_position_score(board)
    score += mobility_score(board)
    score += king_pressure_score(board)

    return score


def move_order_score(board: chess.Board, move: chess.Move) -> int:
    """
    Ordina le mosse per rendere la ricerca più intelligente e veloce.
    """
    score = 0

    moving_piece = board.piece_at(move.from_square)
    captured_piece = board.piece_at(move.to_square)

    # Promozioni
    if move.promotion:
        score += 9000 + PIECE_VALUES.get(move.promotion, 900)

    # Catture buone: MVV-LVA
    if board.is_capture(move):
        if board.is_en_passant(move):
            captured_value = PIECE_VALUES[chess.PAWN]
        elif captured_piece:
            captured_value = PIECE_VALUES[captured_piece.piece_type]
        else:
            captured_value = 100

        attacker_value = PIECE_VALUES[moving_piece.piece_type] if moving_piece else 100
        score += 5000 + 10 * captured_value - attacker_value

    # Scacchi
    try:
        if board.gives_check(move):
            score += 3000
    except Exception:
        board.push(move)
        gives_check = board.is_check()
        board.pop()
        if gives_check:
            score += 3000

    # Arrocco
    if board.is_castling(move):
        score += 1200

    # Sviluppo pezzi minori
    if moving_piece and moving_piece.piece_type in [chess.KNIGHT, chess.BISHOP]:
        if move.from_square in [
            chess.B1, chess.G1, chess.C1, chess.F1,
            chess.B8, chess.G8, chess.C8, chess.F8,
        ]:
            score += 800

    # Centro
    if move.to_square in [
        chess.D4, chess.E4, chess.D5, chess.E5,
        chess.C3, chess.D3, chess.E3, chess.F3,
        chess.C4, chess.F4, chess.C5, chess.F5,
        chess.C6, chess.D6, chess.E6, chess.F6,
    ]:
        score += 300

    # Evita mosse di donna troppo presto, se non sono tattiche
    if moving_piece and moving_piece.piece_type == chess.QUEEN and board.fullmove_number <= 8:
        score -= 500

    return score


def ordered_moves(board: chess.Board):
    moves = list(board.legal_moves)
    moves.sort(key=lambda m: move_order_score(board, m), reverse=True)
    return moves


def minimax(board: chess.Board, depth: int, alpha: int, beta: int, start_time: float) -> int:
    check_time(start_time)

    if depth == 0 or board.is_game_over():
        return evaluate_board(board)

    moves = ordered_moves(board)

    if board.turn == chess.WHITE:
        best_score = -math.inf

        for move in moves:
            board.push(move)
            score = minimax(board, depth - 1, alpha, beta, start_time)
            board.pop()

            best_score = max(best_score, score)
            alpha = max(alpha, score)

            if beta <= alpha:
                break

        return best_score

    else:
        best_score = math.inf

        for move in moves:
            board.push(move)
            score = minimax(board, depth - 1, alpha, beta, start_time)
            board.pop()

            best_score = min(best_score, score)
            beta = min(beta, score)

            if beta <= alpha:
                break

        return best_score


def quick_reasonable_move(board: chess.Board):
    """
    Mossa immediata di emergenza se la ricerca finisce il tempo.
    """
    legal_moves = list(board.legal_moves)

    if not legal_moves:
        return None

    # Matto immediato
    for move in legal_moves:
        board.push(move)
        mate = board.is_checkmate()
        board.pop()

        if mate:
            return move

    # Sceglie la mossa con migliore ordinamento tattico
    legal_moves.sort(key=lambda m: move_order_score(board, m), reverse=True)
    return legal_moves[0]


def choose_humanized_root_move(board: chess.Board, scored_moves):
    """
    Non sempre sceglie matematicamente la prima.
    Così sembra più umano e meno engine.
    Però evita blunder enormi.
    """
    if not scored_moves:
        return None

    if board.turn == chess.WHITE:
        scored_moves.sort(key=lambda x: x[1], reverse=True)
        best_score = scored_moves[0][1]
        candidates = [(m, s) for m, s in scored_moves if s >= best_score - 90]
    else:
        scored_moves.sort(key=lambda x: x[1])
        best_score = scored_moves[0][1]
        candidates = [(m, s) for m, s in scored_moves if s <= best_score + 90]

    candidates = candidates[:3]

    # 80% migliore, 20% una tra le alternative quasi equivalenti
    if len(candidates) == 1 or random.random() < 0.80:
        return candidates[0][0]

    return random.choice(candidates[1:])[0]


def engine_1300_move(board: chess.Board):
    """
    Mini-motore:
    - iterative deepening
    - minimax alpha-beta
    - tempo massimo controllato
    """
    start_time = time.perf_counter()

    best_move = quick_reasonable_move(board)
    best_depth_completed = 0

    for depth in range(1, MAX_SEARCH_DEPTH + 1):
        try:
            check_time(start_time)

            scored_moves = []

            alpha = -math.inf
            beta = math.inf

            for move in ordered_moves(board):
                check_time(start_time)

                board.push(move)
                score = minimax(board, depth - 1, alpha, beta, start_time)
                board.pop()

                scored_moves.append((move, score))

                if board.turn == chess.WHITE:
                    alpha = max(alpha, score)
                else:
                    beta = min(beta, score)

            candidate = choose_humanized_root_move(board, scored_moves)

            if candidate is not None:
                best_move = candidate
                best_depth_completed = depth

        except SearchTimeout:
            break

    return best_move, best_depth_completed


# ============================================================
# API
# ============================================================

@app.get("/")
def home():
    return {
        "status": "Backend Polerio attivo",
        "book_positions": len(MOVE_BOOK),
        "fallback": "mini-engine circa 1300 rapid",
        "max_depth": MAX_SEARCH_DEPTH,
        "time_limit_seconds": SEARCH_TIME_LIMIT,
    }


@app.post("/bot-move")
def bot_move(request: BotMoveRequest):
    print("\n==============================")
    print("Richiesta ricevuta dal frontend")
    print("FEN:", request.fen)

    try:
        board = chess.Board(request.fen)
    except ValueError:
        print("FEN non valida")
        return {
            "move": None,
            "san": None,
            "source": "fen non valida",
        }

    if board.is_game_over():
        return {
            "move": None,
            "san": None,
            "source": "partita finita",
        }

    # 1. Prima prova Polerio vero
    move = choose_from_book(board)
    source = "repertorio Polerio"

    # 2. Se Polerio non conosce la posizione, usa mini-engine intelligente
    if move is None:
        move, depth_completed = engine_1300_move(board)
        source = f"fallback intelligente circa 1300 rapid, depth {depth_completed}"

    if move is None:
        return {
            "move": None,
            "san": None,
            "source": "nessuna mossa disponibile",
        }

    san = board.san(move)

    print("Mossa scelta:", move.uci())
    print("SAN:", san)
    print("Fonte:", source)
    print("==============================")

    return {
        "move": move.uci(),
        "san": san,
        "source": source,
    }