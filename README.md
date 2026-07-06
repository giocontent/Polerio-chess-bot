\# Polerio Chess Bot



A web chess bot inspired by the historical playing style of Giulio Cesare Polerio, one of the most important Italian chess players and theoreticians of the 16th century.



The project combines a React chessboard interface with a Python/FastAPI backend.  

The bot first tries to play from a historical move book built from Polerio-related games. When the current position is not available in the repertoire, it falls back to a lightweight move-selection engine.



\## Live Demo



Frontend:



https://polerio-chess-bot.vercel.app



Backend:



https://polerio-chess-bot.onrender.com



> Note: the online backend is hosted on a free Render instance, so the first request may be slow if the service has been inactive.



\## Project Overview



The idea behind this project is to create a playable chess bot with a historical identity rather than a generic engine.



The bot uses:



\- a historical move book stored in `polerio\_move\_book.pkl`;

\- a FastAPI backend to receive chess positions and return bot moves;

\- a React/Vite frontend with an interactive chessboard;

\- `python-chess` for legal move validation and chess logic;

\- a fallback engine for positions not found in the repertoire.



\## Tech Stack



\### Frontend



\- React

\- Vite

\- JavaScript

\- react-chessboard

\- chess.js

\- Vercel



\### Backend



\- Python

\- FastAPI

\- python-chess

\- Uvicorn

\- Render



\## Repository Structure



```text

Polerio-chess-bot/

│

├── frontend/

│   ├── src/

│   │   ├── App.jsx

│   │   ├── App.css

│   │   └── main.jsx

│   ├── package.json

│   └── vite.config.js

│

├── server.py

├── requirements.txt

├── polerio\_move\_book.pkl

├── .gitignore

└── README.md

