# Account routing: two accounts, one migration

> **Provenance.** Unlike the other references, most of this file is **author-reported experience** (September 2026) rather than behaviour verified in the recorded execution, which ran entirely under one Claude Code login plus `/design-login`. Treat each claim as a lead to confirm against current Anthropic documentation and your own account, not as a spec. Re-verify: the account menu on the web app, the Claude Code `/login` and `/design-login` flows, and Anthropic's help articles on organisation migration.

## Personal and organisation accounts

- A personal account and an organisation account on the **same email address** are separate accounts with separate quota pools. They cannot be merged. On the web they switch through the account menu.
- Claude Design projects belong to one account. There is no share-across-accounts and no transfer button; that is the whole reason this skill exists.

## Running two accounts side by side in Claude Code

- `CLAUDE_CONFIG_DIR` isolates credentials per directory. Two terminals with two config directories run two accounts in parallel with no logout/login cycle.
- Known bug (author-reported): `/login` can report success while the stored OAuth account does not actually change. It is invisible when both accounts share an email — the display looks identical. Confirm which account a session is on by an action whose result differs between accounts (for design work: `list_projects` and check the owner and project set), not by the login banner.
- `/design-login` is separate again (see `designsync-api.md`): the DesignSync tool's authorization is not the session's login, and there is no way to preview which account it will land on. Confirm after the fact with `list_projects`.

## Put the expensive model where it is included

Route by what the step needs, and by which account's plan includes which model:

- **Frontier model:** architecture decisions, the route choice, the namespace analysis, anything irreversible, and the plan reviews where a wrong call costs a migration.
- **Cheaper model:** structural counting, diffs, set arithmetic, file inventories — and **the push itself**, which is contract execution against a printed plan, not judgment.

The recorded execution used a frontier model throughout because the account had it; the point stands for accounts that do not.

## The native personal → organisation migration path

It exists, it moves Claude Design projects, and it is usually a trap. Author-reported terms as of September 2026 — **confirm against current documentation before relying on any of them:**

- It **closes the personal account** and **cancels its subscription** as part of the move.
- It is **one-way** with **no restore**.
- It runs in **one direction only** (personal → organisation).
- **App-store purchases:** if the subscription was bought through a mobile app store, third-party cancellation is not possible from the migration, and the subscription can keep billing after the account has closed.

Document it as a deliberate alternative with its full price. It is the right choice only when you genuinely want the personal account gone and have verified the billing path.

## The reframing that makes the decision tractable

With the ZIP export on disk (and the dated snapshots copied out of `~/Downloads`), **the prototypes are never at risk**. The migration risks the *subscription and the account*, not the work. Once that is clear, the choice between the native path and this skill's push route stops being about losing designs and becomes a question about accounts and money — which is a decision a person can make in a few minutes rather than a week of hedging.
