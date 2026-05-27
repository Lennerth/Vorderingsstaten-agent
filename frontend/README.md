# Buildwise Vorderingsstaten v2 UI

New React/Vite frontend for the FastAPI progress-report backend.

## Development

Build the v2 frontend:

```powershell
npm install
npm run build
```

Start the backend from the repository root:

```powershell
cd ..
python -m app.main
```

Open `http://localhost:8000`. The v2 React UI is the default frontend.

The classic backup UI remains available at `http://localhost:8000/classic`.
To make the classic UI the root page instead, run:

```powershell
python -m app.main --old-frontend
```

Optional dev mode keeps Vite on a separate port:

```powershell
npm run dev
```

Open `http://localhost:5173`. The Vite dev server proxies `/config`, `/health`, `/progress`, and `/progress-report` to `http://localhost:8000`, so local CORS changes are not required.

## Validation

```powershell
npm run build
```
