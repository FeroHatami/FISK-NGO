# NGO Intelligence Hub — Flask Deploy

Single-server setup: Flask serves the React SPA **and** the JSON API.

## Build & run

```bash
# 1. Build the SPA (from project root)
npm install
npm run build:spa     # outputs dist-spa/

# 2. Copy this flask/ folder + dist-spa/ to your server
#    Layout:
#      myapp/
#        app.py
#        requirements.txt
#        data/items.json
#        dist-spa/        <-- from `npm run build:spa`

# 3. Run
pip install -r requirements.txt
python app.py            # http://localhost:5000
```

## API endpoints (wire into your Python pipeline)

| Method | Path              | Purpose                          |
| ------ | ----------------- | -------------------------------- |
| GET    | `/api/items`      | List inbox items (?type=...)     |
| GET    | `/api/items/<id>` | Single item with AI fields       |
| GET    | `/api/briefing`   | Today's AI briefing              |
| POST   | `/api/copilot`    | Ask AI ({ "question": "..." })   |

Search `# TODO` in `app.py` for hook points. Drop your pipeline output
into `data/items.json` (same schema as the React mock data) or replace
the loaders with live DB / pipeline calls.

## Production

Use a real WSGI server:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```
