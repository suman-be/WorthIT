# Agent notes: WorthIT frontend

- Stack: Vite, React 19, TypeScript (strict), React Router, plain CSS with custom properties, Vitest, Testing Library, ESLint.
- Ask before adding any dependency. No UI kits, Tailwind or animation libraries.
- TypeScript is pinned to 6.0.x because typescript-eslint does not support TypeScript 7 yet.
- Before finishing, run `npm run build`, `npm run lint` and `npm test`. All three must pass.

## Rules that must not regress

- Serial number data must never influence the Worth Score. `scoreWatch` in `src/lib/score.ts` only reads `specs`, `market` and `ownership`. Serial results are shown in their own labelled section.
- All weights live in `WEIGHTS`, and they must sum to exactly 1.
- All data access goes through `src/api/`. Only `src/api/` touches `localStorage`, through `storage.ts`.
- No secrets in frontend code or `VITE_*` variables.
- Accessibility: one `<h1 tabIndex={-1}>` per screen. Use `StatusView` for loading, empty and error states. Use `Field` for inputs, which handles the label, hint, error and `aria-describedby`. Use `ErrorSummary` after a failed submit. Use semantic tables with a `<caption>` and `<th scope>`. Never put `onClick` on a `div` or `span`.
- Design tokens are in `src/styles/tokens.css`. Use `--color-border-strong`, not `--color-border`, for form controls and component boundaries, because `--color-border` is below 3:1 contrast.
