# PermitGuard Design System

Source: `ui-ux-pro-max` design-system search for status/incident management, refined for an industrial operations console and the repository UI rules.

## Direction

- Product: pre-shift permit review console for supervisors.
- Style: dense Swiss/minimal operations UI; functional, calm, high contrast.
- Density: 9/10. Motion: 1/10. Variance: 3/10.
- First-screen order: selected permit, primary action, verdict, barriers, evidence, human decision.
- No marketing hero, decorative charts, gradients, nested cards, or hidden errors.

## Tokens

| Role | Value |
|---|---|
| Background | `#F3F4F6` |
| Surface | `#FFFFFF` |
| Surface muted | `#F7F8FA` |
| Ink | `#191C20` |
| Muted text | `#5C6570` |
| Border | `#D7DCE2` |
| Strong border | `#B8C0C9` |
| Primary action | `#C2410C` |
| Destructive | `#B91C1C` |
| Success | `#166534` |
| Warning | `#92400E` |
| Focus | `#0F6CBD` |

- Typography: local `Segoe UI`, Arial, sans-serif; monospace only for IDs, rules, and counters.
- Radius: 4–6px. Repeated finding cards may use 6px.
- Spacing: 4/8px rhythm with 12/16/24px section tiers.
- Shadows: none on page sections; use borders for separation.
- Interaction: 44px minimum controls, 150ms explicit transitions, visible focus.

## Delivery Gate

- Run `python -m ui.visual_qa` after UI changes.
- Verify initial and demo states at 375, 768, 1024, and 1440px.
- Reject console errors, horizontal overflow, missing evidence, or unreachable controls.
- Inspect at least the 375px and 1440px screenshots manually.
- Run Streamlit component tests and the project acceptance suite.
