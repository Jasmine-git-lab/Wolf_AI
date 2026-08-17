# Fix Frontend-Backend Connection

## Steps
- [x] 1. Add `flask-cors` to `requirements.txt`
- [x] 2. Update `agent.py` — enable CORS and add `/health` endpoint
- [x] 3. Update `main.js` — detect Python path, handle spawn errors
- [x] 4. Update `renderer.js` — health-check on startup, better error handling
- [x] 5. Fix Unicode crash in `agent.py` (fire emoji / alarm clock emoji)
- [x] 6. Fix LiveKit CLI subcommand (`sys.argv.append("start")`)
- [ ] 7. Run from correct directory and test (`cd Wolf_AI-main` then `npm start`)

