# Deck sources

`site/index.html` is the interactive deck at https://all-the-vibes.github.io/TokenMasterX/. It is generated and committed, so GitHub Pages can serve it and a pull request shows what changed. Edit the parts in this folder and rebuild. Do not edit `index.html` by hand.

| File | What it is |
| :--- | :--- |
| `body.html` | The slides' markup, with placeholders the build fills in |
| `style.css` | All the styles |
| `app.js` | The deck's behavior: navigation, the inspectors, the segmented controls, the count-ups |
| `build.py` | Assembles `index.html`. Standard library only |
| `checks/` | Optional end-to-end checks that run against the page |

## Build

Run these from the repository root.

```bash
python site/src/build.py            # write site/index.html
python site/src/build.py --check    # fail if site/index.html is not what the build produces
```

The build makes these parts itself, so they follow the repository:

- the wordmark, the header mark and the favicon, drawn by `assets/generate_logo.py`
- the results data, read from `evidence/*/analysis.json`

The two proof slides are written in `build.py`: the claims, what each holds when, and what writing the proofs found. The slides show no counts of theorems, tests or findings, because the point is what the proofs establish. The build checks them against `proofs/` and stops with a message when:

- a theorem or test name on a proof slide no longer exists
- `proofs/README.md` lists a different number of summary claims or findings than the slides do
- a Lean file contains `sorry`
- a placeholder in `body.html` is left unfilled

After you change `proofs/` or `test_proof_conformance.py`, run `python site/src/build.py`. Run `--check` before you commit, to make sure the committed page is the one the build produces.

## Check

The checks need Playwright and Chromium: `pip install playwright`, then `playwright install chromium`. They serve `site/` on a free local port, or test a URL if you pass one.

```bash
python site/src/checks/deck_test.py             # keyboard, hover and pin, controls, copy, layout at seven sizes, reduced motion, no JavaScript, no outside requests
python site/src/checks/swipe_test.py            # touch swipes
python site/src/checks/axe_run.py               # axe-core on every slide (first run `npm install axe-core --no-save --no-package-lock` in site/src/checks)
python site/src/checks/deck_test.py https://all-the-vibes.github.io/TokenMasterX/   # the live page
```

Screenshots go to `site/src/checks/out/`, which git ignores.

## Publish

Only `index.html` is published. The organization disables GitHub Actions for this repository, so nothing deploys it. Copy the file onto the `gh-pages` branch, which holds `index.html` and an empty `.nojekyll`:

```bash
git fetch origin gh-pages
git worktree add ../tm-pages gh-pages
cp site/index.html ../tm-pages/index.html
git -C ../tm-pages add index.html
git -C ../tm-pages commit -m "Update the deck"
git -C ../tm-pages push
```

Skip the `worktree add` line if `../tm-pages` already exists. Pages rebuilds in about a minute. Then check that the live page is the one you built:

```bash
curl -s https://all-the-vibes.github.io/TokenMasterX/ | sha256sum
sha256sum site/index.html
```

If the organization enables Actions for this repository later, a workflow can replace these steps.
