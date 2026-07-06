import { useMemo, useState } from "react";
import { Chess } from "chess.js";
import { Chessboard } from "react-chessboard";

const API_URL =
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8001/bot-move";

function applyUciMove(game, uciMove) {
  if (!uciMove || typeof uciMove !== "string") return null;

  return game.move({
    from: uciMove.slice(0, 2),
    to: uciMove.slice(2, 4),
    promotion: uciMove[4] || "q",
  });
}

function getGameStatus(game) {
  if (game.isCheckmate()) {
    return game.turn() === "w"
      ? "Scacco matto: ha vinto il Nero."
      : "Scacco matto: ha vinto il Bianco.";
  }

  if (game.isStalemate()) return "Stallo.";
  if (game.isThreefoldRepetition()) return "Patta per ripetizione.";
  if (game.isInsufficientMaterial()) return "Patta per materiale insufficiente.";
  if (game.isDraw()) return "Patta.";
  if (game.inCheck()) return "Scacco.";

  return game.turn() === "w" ? "Tocca a te." : "Tocca a Polerio.";
}

export default function App() {
  const [fen, setFen] = useState(new Chess().fen());
  const [thinking, setThinking] = useState(false);
  const [message, setMessage] = useState(
    "Tu giochi con il Bianco. Trascina un pezzo per iniziare."
  );
  const [lastPlayerMove, setLastPlayerMove] = useState("-");
  const [lastBotMove, setLastBotMove] = useState("-");
  const [moveHistory, setMoveHistory] = useState([]);

  const game = useMemo(() => new Chess(fen), [fen]);

  async function askPolerioMove(positionAfterPlayerMove) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => {
      controller.abort();
    }, 5000);

    try {
      setThinking(true);
      setMessage("Polerio sta pensando...");

      console.log("Invio FEN al backend:", positionAfterPlayerMove.fen());

      const response = await fetch(API_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          fen: positionAfterPlayerMove.fen(),
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`Errore backend: ${response.status}`);
      }

      const data = await response.json();
      console.log("Risposta backend:", data);

      const botMoveUci = data.move || data.bot_move || data.uci || data.best_move;

      if (!botMoveUci) {
        throw new Error("Il backend non ha restituito una mossa.");
      }

      const nextGame = new Chess(positionAfterPlayerMove.fen());
      const botMove = applyUciMove(nextGame, botMoveUci);

      if (!botMove) {
        throw new Error(`Mossa del bot non valida: ${botMoveUci}`);
      }

      setFen(nextGame.fen());
      setLastBotMove(`${botMove.san} (${botMoveUci})`);
      setMoveHistory(nextGame.history());

      const status = getGameStatus(nextGame);
      setMessage(
        `Polerio ha giocato: ${botMove.san}. Fonte: ${data.source || "sconosciuta"}. ${status}`
      );
    } catch (error) {
      console.error("Errore durante la mossa di Polerio:", error);

      if (error.name === "AbortError") {
        setMessage(
          "Errore: Polerio non ha risposto entro 5 secondi. Guarda il terminale Python."
        );
      } else {
        setMessage(
          "Errore: il frontend non riesce a completare la mossa del bot. Apri F12 → Console e controlla l'errore rosso."
        );
      }
    } finally {
      clearTimeout(timeoutId);
      setThinking(false);
    }
  }

  function handlePieceDrop(...args) {
    if (thinking) return false;

    let sourceSquare = null;
    let targetSquare = null;

    // React-chessboard nuova versione: passa un oggetto
    if (args[0] && typeof args[0] === "object") {
      sourceSquare = args[0].sourceSquare;
      targetSquare = args[0].targetSquare;
    } 
    // Versioni vecchie: passa sourceSquare, targetSquare
    else {
      sourceSquare = args[0];
      targetSquare = args[1];
    }

    console.log("Drop ricevuto:", sourceSquare, targetSquare);

    if (!sourceSquare || !targetSquare) {
      setMessage("Mossa non riconosciuta. Riprova trascinando il pezzo.");
      return false;
    }

    const nextGame = new Chess(fen);

    const playerMove = nextGame.move({
      from: sourceSquare,
      to: targetSquare,
      promotion: "q",
    });

    if (!playerMove) {
      setMessage("Mossa illegale. Riprova.");
      return false;
    }

    console.log("Mossa giocatore:", playerMove.san);

    setFen(nextGame.fen());
    setLastPlayerMove(`${playerMove.san} (${sourceSquare}${targetSquare})`);
    setMoveHistory(nextGame.history());

    if (nextGame.isGameOver()) {
      setMessage(getGameStatus(nextGame));
      return true;
    }

    askPolerioMove(nextGame);

    return true;
  }

  function resetGame() {
    const newGame = new Chess();

    setFen(newGame.fen());
    setThinking(false);
    setMessage("Nuova partita. Tu giochi con il Bianco.");
    setLastPlayerMove("-");
    setLastBotMove("-");
    setMoveHistory([]);
  }

  return (
    <div style={styles.page}>
      <div style={styles.container}>
        <div style={styles.header}>
          <p style={styles.eyebrow}>Chess bot</p>
          <h1 style={styles.title}>Polerio</h1>
          <p style={styles.subtitle}>
            Bot ispirato al repertorio storico di Polerio.
          </p>
        </div>

        <div style={styles.content}>
          <div style={styles.boardWrapper}>
            <Chessboard
              options={{
                position: fen,
                boardOrientation: "white",
                allowDragging: !thinking && !game.isGameOver(),
                animationDurationInMs: 250,
                onPieceDrop: handlePieceDrop,
              }}
            />
          </div>

          <div style={styles.panel}>
            <h2 style={styles.panelTitle}>Partita</h2>

            <div style={styles.statusBox}>{message}</div>

            <div style={styles.infoRow}>
              <span style={styles.label}>Ultima tua mossa</span>
              <span style={styles.value}>{lastPlayerMove}</span>
            </div>

            <div style={styles.infoRow}>
              <span style={styles.label}>Ultima mossa Polerio</span>
              <span style={styles.value}>{lastBotMove}</span>
            </div>

            <button style={styles.button} onClick={resetGame}>
              Nuova partita
            </button>

            <div style={styles.historyBox}>
              <h3 style={styles.historyTitle}>Mosse</h3>

              {moveHistory.length === 0 ? (
                <p style={styles.emptyHistory}>Ancora nessuna mossa.</p>
              ) : (
                <ol style={styles.historyList}>
                  {moveHistory.map((move, index) => (
                    <li key={`${move}-${index}`}>{move}</li>
                  ))}
                </ol>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    background:
      "radial-gradient(circle at top, #2b211c 0%, #17120f 45%, #080706 100%)",
    color: "#f5eadf",
    fontFamily:
      "Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    padding: "32px",
    boxSizing: "border-box",
  },
  container: {
    width: "100%",
    maxWidth: "1120px",
  },
  header: {
    marginBottom: "28px",
    textAlign: "center",
  },
  eyebrow: {
    margin: 0,
    textTransform: "uppercase",
    letterSpacing: "0.22em",
    fontSize: "12px",
    color: "#d49a68",
  },
  title: {
    margin: "8px 0",
    fontSize: "64px",
    lineHeight: 1,
    letterSpacing: "-0.05em",
    fontWeight: 800,
  },
  subtitle: {
    margin: "0 auto",
    maxWidth: "620px",
    color: "#cdbfb2",
    fontSize: "16px",
  },
  content: {
    display: "grid",
    gridTemplateColumns: "minmax(320px, 620px) minmax(280px, 1fr)",
    gap: "28px",
    alignItems: "start",
  },
  boardWrapper: {
    width: "100%",
    maxWidth: "620px",
    background: "rgba(255, 255, 255, 0.06)",
    padding: "16px",
    borderRadius: "24px",
    boxShadow: "0 24px 80px rgba(0, 0, 0, 0.45)",
    boxSizing: "border-box",
  },
  panel: {
    background: "rgba(255, 255, 255, 0.08)",
    border: "1px solid rgba(255, 255, 255, 0.12)",
    borderRadius: "24px",
    padding: "22px",
    boxShadow: "0 24px 80px rgba(0, 0, 0, 0.35)",
  },
  panelTitle: {
    margin: "0 0 16px",
    fontSize: "28px",
  },
  statusBox: {
    minHeight: "72px",
    background: "rgba(0, 0, 0, 0.28)",
    borderRadius: "16px",
    padding: "16px",
    marginBottom: "18px",
    color: "#fff4e8",
    lineHeight: 1.45,
  },
  infoRow: {
    display: "flex",
    justifyContent: "space-between",
    gap: "12px",
    borderBottom: "1px solid rgba(255, 255, 255, 0.1)",
    padding: "12px 0",
  },
  label: {
    color: "#cdbfb2",
    fontSize: "14px",
  },
  value: {
    fontWeight: 700,
    textAlign: "right",
  },
  button: {
    width: "100%",
    marginTop: "18px",
    padding: "13px 16px",
    borderRadius: "999px",
    border: "none",
    cursor: "pointer",
    background: "#d49a68",
    color: "#17120f",
    fontWeight: 800,
    fontSize: "15px",
  },
  historyBox: {
    marginTop: "22px",
  },
  historyTitle: {
    margin: "0 0 8px",
    fontSize: "18px",
  },
  emptyHistory: {
    color: "#cdbfb2",
    margin: 0,
  },
  historyList: {
    maxHeight: "180px",
    overflowY: "auto",
    paddingLeft: "22px",
    color: "#f5eadf",
    lineHeight: 1.7,
  },
};