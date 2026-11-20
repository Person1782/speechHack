# Heckle & Hint

A bilingual, comedian-led pub quiz for bars in Ho Chi Minh City. The quiz creates the setup; the comedian delivers the punchline.

The host runs the night from their phone. Teams share one phone, and an optional big screen shows questions, approved audience material, and scores. Hosts can review answers privately before revealing them and control the pace throughout the night.

## What is included

- English and Vietnamese interfaces, room codes, QR joining, and persistent team sessions.
- Host controls for answering, locking, revealing, pausing, and advancing questions.
- Private answer distributions, preparation notes, and audience-interaction preferences.
- Question creation and editing, including trivia and moderated audience polls.
- Reusable personal question decks, deck selection when creating a room, and saving a room's question set as a deck.
- Host approval before audience-written poll answers become public.
- Scoring, streaks, leaderboards, demo teams, and simulated answering.
- Polling-based synchronization, reconnect indicators, and server-controlled timers.

Answer choices use lettered cards rather than the four-color geometric quiz-button pattern.

## Personal decks and access

There are no accounts. The browser stores a random private library key; the server associates saved decks with a hash of that key. Reuse the same browser to find your decks. Clearing browser storage loses access to that library. Decks remain available for future nights; room data expires after 48 hours.

The host link contains a separate room-control key. Anyone with that link can control the room. Player and screen responses omit private notes and unrevealed answers.

## Run locally

Requirements: Python 3.11 or newer, Node.js 20 or newer, Yarn Classic, and MongoDB running locally or available through a connection URL.

1. Configure the backend:

   ```sh
   python3 -m venv backend/.venv
   backend/.venv/bin/pip install -r backend/requirements.txt
   cp backend/.env.example backend/.env
   ```

2. Configure and install the frontend:

   ```sh
   cp frontend/.env.example frontend/.env
   cd frontend
   yarn install --frozen-lockfile
   ```

3. Start the backend in one terminal:

   ```sh
   cd backend
   .venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001
   ```

4. Start the frontend in another terminal:

   ```sh
   cd frontend
   yarn start
   ```

Open `http://localhost:3000`. For testing across phones, use the computer's reachable LAN address in `REACT_APP_BACKEND_URL` and the corresponding frontend origin in `CORS_ORIGINS`, then restart the frontend. HTTPS is needed for browser capabilities such as screen wake lock on non-localhost origins.

## Configuration

Backend variables are loaded from `backend/.env`:

- `MONGO_URL`: MongoDB connection URL.
- `DB_NAME`: application database name.
- `CORS_ORIGINS`: comma-separated allowed frontend origins.
- `YDC_API_KEY`: optional search integration key; omit it for the prepared-content quiz and deck workflows.

The frontend reads `REACT_APP_BACKEND_URL` at build/start time. Set this to the backend origin without a trailing `/api`. Keep actual `.env` files and credentials out of version control.

## Routes

| Route | Purpose |
| --- | --- |
| `/` | Landing and room-code entry |
| `/host` | Host setup and deck selection |
| `/host/CODE?key=HOST_KEY` | Private host console and question manager |
| `/join/CODE` | Join a team |
| `/play/CODE` | Team phone |
| `/screen/CODE` | Optional big screen |

## Verification

With MongoDB and the backend running, and `frontend/.env` configured for the intended test server:

```sh
cd backend
.venv/bin/python -m pytest test_decks.py tests/test_tier1.py tests/test_tier2.py -q
```

Deck tests use a disposable MongoDB database. Existing integration tests create test rooms on the running API; the Tier 2 tests use the URL from `frontend/.env`, so check that value before running them.

Build the frontend:

```sh
cd frontend
yarn build
```

Vietnamese comedy phrasing is marked for native-speaker review. A local or automated browser check does not replace a rehearsal on the venue's actual phones, display, and network.
