# Snooker scoreboard

A compact, stateful scoreboard for a game of snooker. Rather than showing just two totals, it shows the **balance of the frame**: who is at the table, what can still be scored, and when one player has moved beyond the other's reach.

**[Open the scoreboard](https://smcateer.github.io/snooker-scoerboard/scorecard.html)** · [Site root](https://smcateer.github.io/snooker-scoerboard/)

## Design

The score bar is centred on half the possible frame total. Instead of showing an absolute target, it displays each player's distance to that midpoint: unsigned numbers show the points required to reach it (a draw if the total is even), and a `+` shows how far the player has passed it. With a total of 120, the midpoint is 60: scores 30, 60 and 65 show `30`, `0` and `+5`. With an odd total such as 147, the midpoint is 73.5 and the display uses half-points. The numbers are not a direct count of snookers needed. Each player's points fill in from opposite ends; the unclaimed portion is black. After a red, a 50/50 hatched area shows the striker's *provisional* colour opportunity, which is not yet part of their scored total. The bar adjusts when points become unavailable. An arrow identifies the player at the table.

The UI uses contextual buttons (ball colours, Miss, Foul), with name editing, manual corrections and history in menus. Break, reds remaining and any free-ball state are shown without explanatory clutter. Frame and Undo state persist in browser localStorage.

## Development — AI-assisted / vibe coded

This project is **vibe coded**. The initial proof of concept was built with GitHub Copilot in VS Code. The current interface and state model were redesigned iteratively with ChatGPT, including rule handling, visual adjustments and a Chromium regression suite.

The author defined the goals, evaluated the interface and commissioned the fixes; AI generated much of the implementation **and the tests**. They are useful regression checks, not independent rules certification. The project is a scoring aid, not referee-grade software.

## Files

```text
scorecard.html                    Complete self-contained HTML/CSS/JavaScript app
index.html                        Redirect from the site root to scorecard.html
.nojekyll                         Disable Jekyll for this static site
requirements-dev.txt             Pinned Python/Playwright test dependencies
.devcontainer/devcontainer.json  VS Code development-container environment
.github/workflows/tests.yml      GitHub Actions browser regression tests
tests/test_scoreboard.py         Browser integration tests (111 scenarios)
```

## Running the scoreboard

Open `scorecard.html` in a modern browser, or run this in the repo directory:

```bash
python -m http.server 8000
```

Then open http://localhost:8000/. There is **no frontend build, npm install or compilation**.

## Test environment and commands

Use Python 3.12 (the version used in GitHub Actions) and Playwright 1.57.0. From the repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m playwright install --with-deps chromium
python tests/test_scoreboard.py
```

On Windows use `.venv\Scripts\activate` and `python -m playwright install chromium` (system dependencies differ). On Linux, `--with-deps` might require sudo. If system Chromium is on PATH it is used; otherwise Playwright's bundled Chromium is used.

**VS Code Dev Containers:** Install the Dev Containers extension, open the repository, choose **Dev Containers: Reopen in Container**, then run `python tests/test_scoreboard.py`. The `.devcontainer/devcontainer.json` config installs dependencies and Chromium automatically.

The runner reads **`scorecard.html`** from the repository root and adds a test hook to an **in-memory copy**. It does not modify production HTML. It checks scoring, fouls, free balls, last-red transitions, re-spotted black, undo, saved state and narrow-screen rendering, plus deterministic randomised frames. Output is written to `test-results/results.json`; the command **exits non-zero if any assertion fails or any JavaScript exception occurs**. Two unsupported rules are counted separately rather than treated as passing.

The [GitHub Actions workflow](https://github.com/smcateer/snooker-scoerboard/actions/workflows/tests.yml) runs the same command on pushes to main, on pull requests, and on manual dispatch; it uploads the report as an artifact.

## GitHub Pages

Keep `scorecard.html` in the repository root: this preserves the existing URL:

https://smcateer.github.io/snooker-scoerboard/scorecard.html

The root `index.html` redirects to it. Publishing via **Settings → Pages → Deploy from a branch → main → /(root)** automatically publishes the static files on a push to main. The regression workflow is **CI only**; it does not deploy the site or change its GitHub Pages configuration. If Pages is set to publish from a different branch/folder or via GitHub Actions, choose `main` and `/(root)` to use this layout.

## Implemented and unsupported rules

The scoreboard handles ordinary red/colour scoring, final colours, misses, foul penalties (including nominated colour), free balls and tied-frame re-spotted blacks.

Known gaps:
- **Foul and a miss** ball-position restoration.
- Multiple reds in a single stroke.
- Certain referee-only decisions, conceded or awarded frames.

Do not use it as an authoritative adjudication tool. Rules reference: [WPBSA official rules](https://www.wpbsa.com/rules/).
