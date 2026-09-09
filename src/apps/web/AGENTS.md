# Web App Guidance

The Omnix web app is React/TypeScript under `src/apps/web`.

- Inspect the owning component, styles, tests, API types, and theme overrides before editing.
- Prefer focused component/unit tests, then package build/typecheck when shared interfaces or styles change.
- Run package commands from repository root using `npm --prefix src/apps/web ...`.
- Keep light/dark/Aurora/Liquid Glass behavior and accessibility/readability consistent when touching shared styles.
- If API contracts change, update/regenerate the checked-in OpenAPI/types using the repository's existing workflow rather than hand-maintaining incompatible generated shapes.
- Review the complete final diff for unrelated CSS/theme changes and stale labels or selectors.