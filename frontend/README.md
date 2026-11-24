# WorthIT frontend

Calculates a Worth Score (0 to 100) for a watch you own or are thinking of buying.

## Run it

Requires Node.js 20.19+ or 22.12+ (developed on Node 24).

```sh
cd frontend
npm install
npm run dev        # http://localhost:5173
```

| Command | What it does |
| --- | --- |
| `npm run dev` | Development server |
| `npm run build` | Type check (`tsc -b`) and production build to `dist/` |
| `npm run preview` | Serve the production build |
| `npm run lint` | ESLint |
| `npm test` | Vitest, run once |
| `npm run test:watch` | Vitest in watch mode |

## Routes

| Route | Screen |
| --- | --- |
| `/` | Add a watch: enter a serial number; the server identifies the model and returns the serial checks |
| `/watches/:watchId` | Watch detail: Worth Score, breakdown, resale value, cost of ownership, serial check |
| `/preferences` | Preferences: budget and holding period, shared with every score (`/context` redirects here) |
| `/my-watches` | Saved watches and a side-by-side comparison of two or three |

## Project layout

```
src/
  api/          All data access. Mock implementations with TODO(backend) markers.
    http.ts           fetch wrapper: maps every server outcome to data or an ApiError
    schema.ts         runtime validation of server responses
    watches.ts        watch lookup by ID
    serial.ts         serial lookup: identifies the model + returns checks (checks never used for scoring)
    savedWatches.ts   "My watches"
    userContext.ts    budget and holding period
    storage.ts        safe localStorage wrapper with in-memory fallback
  lib/
    score.ts      Pure scoring engine (WEIGHTS, group scores, resale, cost of ownership, label)
    validation.ts Pure form validation
    format.ts     Number, currency and date formatting
  context/      Shared user context (React context)
  components/   StatusView, Field, ErrorSummary, tables, Layout and so on
  pages/        One component per screen
  styles/       tokens.css (design tokens) and global.css
```

## Scoring model

Weights live in `WEIGHTS` in `src/lib/score.ts`: Specs 25%, Market 30%, Ownership 20%, Context 25%.
Each group scores 0 to 100. The Worth Score is the rounded weighted sum.
Strong is 70 or more, Fair is 45 to 69, Weak is below 45.

- **Resale value** = price × (retention ÷ 100) × (1 + trend × 0.25)^years. The trend is capped at ±50%.
- **Total cost of ownership** = (service cycles × service cost) + value lost.
  Service cycles = whole intervals within the holding period. Value lost = price − resale value. It is negative when the watch is expected to gain value.

The serial number is only used to identify which model the watch is. The score is then calculated from that model's data and your preferences. Details about the individual watch, such as production year, authenticity, service history and stolen status, never reach the scoring engine. `scoreWatch` reads only `specs`, `market` and `ownership`, and tests check this.

## Server responses

When `VITE_API_BASE_URL` is set, `POST /serial-lookups { serial }` is called. Each possible response is handled as follows:

| Response | What the user sees |
| --- | --- |
| 200 with valid body | Identified watch, Worth Score, serial check, Save and breakdown actions |
| 200 with wrong shape or non-JSON | "Format this app does not understand" error with Try again |
| 400 / 422 | The server's message shown inline on the serial field |
| 401 / 403 | Sign-in message |
| 404 | "No watch found" with guidance on where to find the serial |
| 429 | "Too many lookups", using `Retry-After` to say how long to wait |
| 5xx | "Not caused by anything you did", with Try again |
| Network failure / 10 s timeout | Connection or timeout message, with Try again |

## Mock behaviour (development only)

- Five sample watches are in `src/api/mockWatches.ts`. Their figures are plausible estimates, not market data.
- Serial lookups are deterministic. The Add screen lists sample serials while the mock is active. A serial starting with `0000` is not found. A serial ending in `99` is reported stolen. Any other valid serial maps to one of the five sample watches.
- Add `?mockFail=watches`, `serial`, `saved` or `context` (comma-separated) to the URL in `npm run dev` to make that API area fail. Use it to check the error and retry states.
- If the browser blocks `localStorage`, data is kept in memory for the session and a notice is shown.

## Environment and secrets

- Copy `.env.example` to `.env.local` (gitignored) for local overrides.
- Every `VITE_*` variable ends up in the public JavaScript bundle. Use it for public configuration only, such as `VITE_API_BASE_URL`.
- Never put API keys or credentials in frontend code or `VITE_*` variables. Calls that need credentials, such as manufacturer databases and stolen-watch registries, must go through the backend.

## Backend integration

Search for `TODO(backend)` in `src/api/`. Each function shows the endpoint it should call. The UI depends only on the function signatures, so you can replace the function bodies without changing any components.
