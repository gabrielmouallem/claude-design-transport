# Alternatives to the push route — and when each is right

> **Verified as of 2026-09-15** for the comparison against the push route; the third-party landscape notes are author observations from the same period and go stale fast. Re-verify: check whether the DesignSync tool still exposes `write_files` before choosing anything below.

The push route preserves the *source* layer — token indirection, prop contracts, every state, the card-registration markers — because it writes bytes. Every alternative below trades some of that away. Sometimes that trade is correct.

## Element / browser capture

Claude Design's web capture, and third-party "grab this UI" extensions, turn a rendered page into editable frames.

- **Right when:** the goal is to **redesign** screens, not preserve them. You want the look as a starting point and intend to change it.
- **Wrong when:** fidelity matters. Capture preserves rendered pixels and destroys the semantic layer: `var(--token)` collapses to a hex that no longer knows it is reserved for anything; component prop contracts become divs; keyboard behaviour and every state not painted at capture time are gone.
- **One genuine advantage:** it is immune to the CDN problem — rendering already happened before capture. Dead, but correct-looking.
- **Risk surface:** a third-party extension with broad host permissions on a machine logged into production accounts is a real exposure, and auto-updates mean benign today is not benign tomorrow. Prefer the first-party capture if you capture at all.

## Prompt-based reproduction into a fresh project

Export the ZIP, upload it, and prompt the model to rebuild the project faithfully. This is the approach the push route exists to replace.

- **Why it fails for transport:** the uploads folder is an *ingestion* channel — the model reads and re-emits an interpretation. Fidelity is probabilistic, drift is silent, and the compiled artifacts (bundle, manifest) cannot be reproduced by prompting at all.
- **The fidelity machinery, kept for when the door really is locked:** if no write API is available — a different tool, a locked-down account, a platform change — the following was built and is still the right shape:
  - a **tripwire list**: concrete facts that must survive (token names and values, component names and props, exact copy, counts) checked after each round;
  - a **canary section**: a deliberately distinctive, low-value element whose loss reveals drift early;
  - a **divergence report** the model must fill in — what it changed, what it could not reproduce, what it invented — so omissions are declared instead of hidden;
  - a **local diff harness** that scores the reproduction against the source structurally (token sets, component inventories, page lists) rather than by eye.
  That was good work aimed at the wrong target. Use it as the fallback, not the route.

## Deploy-and-recapture

Deploy the prototype through a platform integration, then capture the live site back into Claude Design.

- The integration is a **deploy target**: one-way, and it does not transport editable state. You end up with capture's losses plus a hosting dependency.
- Right only as a way to *publish* a prototype, never as a way to *move* one.

## Open-source reimplementations

Reimplementations of the Claude Design workflow exist that accept a subscription-authenticated CLI rather than an API key.

- **Relevant when:** the goal is provider or tooling choice rather than transport.
- **Caution:** repositories claiming to be "the open source alternative" often come with SEO fork swarms — many near-identical forks with tuned names. Identify the upstream by commit history and maintainers before trusting one, and read what its CLI authenticates against before pointing it at an account.

## Decision shortcut

| You want to… | Use |
|---|---|
| Keep the system exactly as it is, in another account or project | **Push route** (this skill) |
| Redesign from the current look | Capture (first-party) |
| Move when there is no write API | Prompt reproduction with the fidelity machinery, and expect drift |
| Publish a prototype for others to view | Deploy integration — not a transport |
| Leave the platform | A reimplementation, after identifying its upstream |
