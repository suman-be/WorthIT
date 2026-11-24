# Build a Watch Valuation App in React
In the `frontend` folder of this project, build the user interface for our watch valuation app using React. This is the actual working application, not a marketing or landing page.

## 1. What the app does
A user adds a watch they own or are considering buying. The app calculates a **Worth Score from 0 to 100**, based on four weighted groups:

- **Specs (25%)** – Utility: movement, case size, material and water resistance.
- **Market (30%)** – Value retention: `resale_retention_pct` and `popularity_trend`.
- **Ownership (20%)** – True cost: `service_interval_years` and `service_cost`.
- **Context (25%)** – Personal fit: budget and `holding_period_years`.
Example watch data:

```
{
  "brand": "...",
  "model": "...",
  "reference": "...",
  "specs": {
    "movement": "...",
    "case_mm": 40,
    "material": "...",
    "water_resistance_m": 100
  },
  "market": {
    "price": 5200,
    "resale_retention_pct": 78,
    "popularity_trend": 0.12
  },
  "ownership": {
    "service_interval_years": 5,
    "service_cost": 450
  },
  "context": {
    "budget": 6000,
    "holding_period_years": 5
  }
}
```

### Important: Serial number handling
A serial number identifies a specific physical watch. It can provide information about:

- Production year
- Production batch
- Authenticity
- Service history
- Stolen-watch checks
**The serial number must never influence the Worth Score or its calculation.**

Display serial lookup results in their own clearly labelled section with a separate heading.

## 2. Screens and routes

### Screen 1: Add a watch
Allow users to search for a watch using:

- Brand
- Model
- Reference number
Include an optional serial number field.

Provide a short hint explaining what the serial number checks and clarify that it does not affect the Worth Score.

### Screen 2: Watch detail
Display:

- The Worth Score prominently, from 0 to 100.
- A word label: Strong, Fair or Weak.
- A breakdown of all four scoring groups.
- Each group's individual score and weight.
- One plain-language sentence explaining why each group received its score.
- Estimated resale value after the selected holding period.
- Total cost of ownership over the holding period.
Calculate total cost of ownership using:

`(service cycles × service cost) + value lost`

Include serial check results in a separate section when a serial number was provided.

### Screen 3: Your context (`/context`)
Provide form fields for:

- Budget
- Holding period (years)
Changes must update the Worth Score immediately and be shared with the watch detail screen.

### Screen 4: My watches
Display a saved list of watches.

Allow users to select two or three watches for side-by-side comparison.

The comparison must use a real semantic HTML `<table>`.

### Loading, empty and error states
Every screen must support:

- Empty states
- Loading states
- Retryable error states
Create one reusable `StatusView` component for these states.

Error messages must explain what went wrong and how the user can fix it.

## 3. Technology stack
Use:

- Vite
- React 19
- TypeScript (strict mode)
- React Router
- Plain CSS with custom properties
- Vitest
- Testing Library
- ESLint
Use function components and React hooks only.

Do not install any dependencies beyond Vite, React, React Router, TypeScript, Vitest, Testing Library and ESLint without asking me first.

Do not use:

- UI component libraries
- Tailwind CSS
- Animation libraries

### CSS tokens
Store design tokens in:

`src/styles/tokens.css`

## 4. Scoring logic
Implement the scoring engine in:

`src/lib/score.ts`

Requirements:

- Use pure functions.
- Define all weights in one `WEIGHTS` configuration object.
- Return individual group scores.
- Include a plain-language reason for each group.
- Return the total Worth Score (0–100).
- Return the estimated resale value.
- Return the total cost of ownership.
- Return the Strong, Fair or Weak label.
The four groups must use the following weights:

Group | Weight

Specs | 25%

Market | 30%

Ownership | 20%

Context | 25%

**Total** | **100%**
Serial number data must never enter the scoring calculation.

## 5. Data and storage
All data access must go through `src/api/`.

Organise the API layer into separate modules for:

- Watches
- Serial number lookups
- Saved watches
- User context
Provide five realistic, strongly typed mock watches.

Leave clear TODO comments indicating where the real backend endpoints should be integrated.

### Local storage
Store saved watches and user context in `localStorage`, with all storage access handled behind `src/api/`.

The application must handle unavailable or inaccessible browser storage without crashing.

The API layer should be structured so that local mock implementations can later be replaced with real backend integrations without requiring major frontend changes.

## 6. Security and secrets

- Never include API keys or secrets in frontend code.
- Store local development secrets in a gitignored `.env.local` file.
- Never expose private credentials through frontend environment variables.

## 7. Tests
Use Vitest.

### Scoring tests (`score.ts`)
Test that:

1. All scoring weights sum to exactly 1.
2. The total score always stays between 0 and 100.
3. Strong, Fair and Weak boundaries are correct.
4. Resale value calculations are correct.
5. Total cost of ownership calculations are correct.
6. Changing serial number data never changes the Worth Score.

### Component tests
Also test:

- Form validation messages.
- Live Worth Score updates when the user changes their context.

## 8. HTML and accessibility
Follow **WCAG 2.2 AA** strictly.

### Structure and controls

- Use semantic HTML landmarks.
- Include a skip link.
- Use exactly one `<h1>` per screen.
- Keep heading levels in the correct order.
- Use `<button>` for actions.
- Use `<a>` or React Router `<Link>` for navigation.
- Never attach `onClick` handlers to `<div>` or `<span>` elements.
- Every input must have a visible `<label>`.
- Use the correct input type.
- Include appropriate autocomplete attributes.
- Link input hints using `aria-describedby`.

### Validation and announcements

- Display validation errors as text next to their corresponding fields.
- Show a validation summary at the top of the form when submission fails.
- Never rely on colour alone to communicate errors.
- Announce Worth Score changes using an `aria-live="polite"` region.

### Data accessibility

- The score breakdown must use a semantic HTML table.
- The watch comparison must use a semantic HTML table.
- Both tables must include a `<caption>` and appropriate `<th scope>` attributes.

### Focus and keyboard accessibility

- When navigating between routes, move focus to the new screen's `<h1>` using `tabindex="-1"`.
- Update `document.title` on every route change.
- Ensure the entire application is usable with a keyboard.
- Provide clearly visible `:focus-visible` outlines.

### Sizing and user preferences

- Text contrast must be at least 4.5:1.
- UI component contrast must be at least 3:1.
- Touch targets must be at least 44 × 44px.
- Support a minimum viewport width of 320px.
- Support 200% zoom without horizontal scrolling.
- Respect `prefers-reduced-motion`.
- Respect `prefers-color-scheme`.

## 9. Design requirements
The design should be minimal, calm and functional, like a tool used to make a financial decision.

Numbers should be the visual priority, with clear units such as:

- €
- %
- Years
Use tabular figures for numerical values.

### Typography
Font family:

`"Avenir Next", "Segoe UI", system-ui, sans-serif`

Use:

`font-variant-numeric: tabular-nums`

Font scale (in rem):

`0.8, 1, 1.25, 1.5625, 1.953, 2.441, 3.052, 3.815, 4.768`

### Colours
**Light theme**

Token | Colour

Background | `#F7F6F2`

Surface | `#FFFFFF`

Text | `#1B1F1E`

Muted text | `#4C544F`

Border | `#C9CEC8`

Accent | `#0F6B5C`

Focus | `#0B5145`

Strong | `#0E5A4A`

Fair | `#5D4A18`

Weak | `#8A2F2F`
**Dark theme**

Token | Colour

Background | `#121614`

Surface | `#1B211E`

Text | `#F0F2EF`

Muted text | `#B6C0B8`

Border | `#36413A`

Accent | `#7FD3BD`

Focus | `#9FE5D2`

Strong | `#8FDCC6`

Fair | `#E2C37A`

Weak | `#EF9E9E`

### Spacing and radii
Use the following spacing values:

`4, 8, 12, 16, 24, 32, 48, 64px`

Border radii:

`4px, 8px`

### Design restrictions
Do not use:

- Gradients
- Glassmorphism
- Glowing borders
- Emojis
- Decorative icons
- Grids of identical shadowed cards
- All-caps eyebrow labels
- Arrow symbols such as `→` on buttons
Use clear, functional labels such as:

- "Holding period (years)"
- "Save watch"
- "Compare selected"
Avoid marketing language. This is a working application, not a promotional website.

## 10. Implementation process
Follow these steps:

1. Inspect the existing project structure and the `frontend` folder.
2. Build the complete application inside `frontend`.
3. Implement all screens, routes, components and scoring logic.
4. Implement the mock API and local storage.
5. Implement the accessibility requirements.
6. Write and run all required tests.
7. Run the following commands:

```
npm run build
npm run lint
npm test
```

1. Fix all errors and failures before finishing.

## 11. Final deliverables
When finished, provide:

### A. How to run the application
Include the commands needed to install dependencies and start the development server.

### B. Accessibility checklist
Provide a checklist covering every accessibility requirement in this prompt.

Mark each requirement as:

- Passed
- Not implemented
- Partially implemented
Explain any requirements that could not be met and why.

### C. Remaining backend TODOs
List all TODOs that remain for integration with the real backend, including:

- Watch search and retrieval endpoints.
- Serial number lookup and verification.
- Real scoring and valuation data.
- Market data and comparable sales.
- Saved watch persistence.
- User context persistence.
**Important:** Do not claim that tests, builds, linting or accessibility checks passed unless they were actually run and verified.