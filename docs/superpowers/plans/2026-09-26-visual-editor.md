# Visual Website Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an owner-only Decap CMS editor that manages all portfolio content, creates previewable drafts, sanitizes uploaded media, and publishes approved changes to GitHub Pages.

**Architecture:** GitHub remains the source of truth and `master` remains the production branch. Jekyll renders structured site settings plus one Markdown file per work; Decap CMS writes drafts through Netlify Identity and Git Gateway, Netlify supplies pull-request previews, and GitHub Actions sanitizes and validates each draft before merge.

**Tech Stack:** Jekyll/Liquid, YAML front matter, Decap CMS 3.8.3, Netlify Identity 1.9.2, Netlify Git Gateway, Python 3 standard library, Pillow 11.3.0 for verification, Ruby YAML, GitHub Actions, Playwright 1.55.

**Spec:** `docs/superpowers/specs/2026-09-25-visual-editor-design.md`

## Global Constraints

- Only the GitHub account `YichuanLi98` may edit; Netlify registration is invite-only and GitHub is the only external identity provider.
- `master` contains published content only and deploys to `https://yichuanli98.github.io/` through GitHub Pages.
- Netlify preview URLs are unlisted but do not require login.
- Canonical content stays in Git; no database or remote media store is introduced.
- The editor covers all copy, metadata, navigation, contact links, photography, and painting, but not CSS, JavaScript, templates, or infrastructure settings.
- Media is limited to JPEG, PNG, and WebP; public media must contain no EXIF, IPTC, XMP, comment, or time metadata.
- Preserve the current visual direction, responsive gallery, lightbox, and configurable painting “coming soon” state.
- Do not commit OAuth secrets, Netlify credentials, GitHub tokens, or user email addresses.

## Review Focus

- A work referencing a missing or unsupported image must fail validation with the work path and field name; Task 4 adds this test.
- Duplicate `order` values or more than one visible featured work must fail deterministically; Task 1 adds these tests.
- Zero visible photographs must produce a clear validation error instead of a broken hero; Task 1 adds this test.
- JPEG, PNG, and WebP metadata removal must preserve decodable image bytes and be idempotent; Task 4 adds these tests.
- A gallery with a non-multiple-of-eight item count must remain usable on mobile and in the lightbox; Task 5 adds a nine-item browser fixture test.

---

## File Structure

- `_data/site.yml`: owner-editable global copy, navigation, links, hero selection, and painting state.
- `_works/*.md`: one owner-editable work per file with category, image, accessibility, ordering, and visibility fields.
- `index.html`: Liquid renderer for site settings, photography, painting, and lightbox markup.
- `admin/index.html`: pinned Decap CMS and Netlify Identity shell.
- `admin/config.yml`: Git Gateway, editorial workflow, media, collections, and Chinese field labels.
- `admin/preview.js`, `admin/preview.css`: CMS preview templates and portfolio styling.
- `scripts/validate_content.rb`: structured-content validation with stable error messages.
- `scripts/sanitize_media.py`: lossless metadata removal and check/write CLI.
- `requirements-dev.txt`: pinned Pillow dependency used only to verify sanitized files decode.
- `tests/test_content_model.py`, `tests/test_media_sanitizer.py`, `tests/test_cms_config.py`: focused contracts.
- `tests/test_gallery.py`: rendered Jekyll output and asset contract.
- `tests/gallery.spec.js`, `playwright.config.js`: desktop/mobile browser behavior.
- `.github/workflows/cms-draft.yml`: same-repository CMS branch sanitization, validation, and status reporting.
- `.github/workflows/site-quality.yml`: read-only production and manual verification.
- `netlify.toml`: Jekyll build and preview configuration.
- `docs/editor-operations.md`: login, drafting, preview, publish, rollback, and recovery runbook.

### Task 1: Introduce the content model and migrate existing works

**Files:**
- Create: `_data/site.yml`
- Create: `_works/01-paris-sunset.md` through `_works/08-birds-over-sea.md`
- Create: `tests/test_content_model.py`
- Modify: `_config.yml:228-241`
- Move: `assets/images/photography/*.jpeg` to `assets/images/works/*.jpeg`

**Interfaces:**
- Produces: `site.data.site` with `owner`, `seo`, `navigation`, `hero`, `sections`, `footer`, and `contact`; `site.works` entries with `title`, `category`, `image`, `alt`, `description`, `location`, `date`, `order`, `featured`, and `visible`.
- Consumes: no new interfaces.

- [ ] **Step 1: Add failing content-model tests**

In `tests/test_content_model.py`, load YAML through Ruby’s safe YAML parser and parse work front matter. Assert exactly eight works, allowed categories `{photography, painting}`, unique `(category, order)` pairs, exactly one visible featured photograph, at least one visible photograph, required non-empty `title`, `image`, and `alt`, and the complete global key set above. Add separate fixtures/tests that assert duplicate order, two featured photographs, and zero visible photographs are rejected by `scripts/validate_content.rb` with exit code `1` and messages containing the offending field.

- [ ] **Step 2: Run the tests and confirm the expected failure**

Run: `python3 -m unittest tests.test_content_model -v`

Expected: FAIL because `_data/site.yml`, `_works/`, and `scripts/validate_content.rb` do not exist.

- [ ] **Step 3: Create the migrated data and collection**

Add `works: { output: false }` under `_config.yml` collections. Populate `_data/site.yml` with the current text from `index.html`, including `Yichuan Li`, `Visual journal`, `Selected works`, `Photography & Painting`, both section headings, footer copy, and `sections.painting.coming_soon: true`.

Create the eight work files with orders `1` through `8`; only `01-paris-sunset.md` has `featured: true`. Use the current eight alt descriptions verbatim. Move images to matching paths `assets/images/works/photo-01.jpeg` through `photo-08.jpeg` and update each `image` value to an absolute site path.

- [ ] **Step 4: Implement `scripts/validate_content.rb`**

Provide `validate_site(data: Hash) -> Array<String>`, `validate_works(works: Array<Hash>) -> Array<String>`, and a CLI that accepts `--site PATH --works DIR`. Errors must include file/field context; success prints `content validation: OK` and exits `0`.

- [ ] **Step 5: Verify the model and existing suite**

Run: `ruby scripts/validate_content.rb --site _data/site.yml --works _works && python3 -m unittest tests.test_content_model tests.test_gallery -v`

Expected: all tests pass and the validator prints `content validation: OK`.

- [ ] **Step 6: Commit the content migration**

```bash
git add _config.yml _data/site.yml _works assets/images/works scripts/validate_content.rb tests/test_content_model.py
git commit -m "feat: model portfolio content for editing"
```

### Task 2: Render the portfolio from structured content

**Files:**
- Modify: `index.html:1-122`
- Modify: `assets/css/gallery.css:244-345`
- Modify: `assets/js/gallery.js:1-41`
- Modify: `tests/test_gallery.py`

**Interfaces:**
- Consumes: `site.data.site` and `site.works` from Task 1.
- Produces: rendered `.gallery-item[data-full][data-alt]` buttons for all visible works and one shared `#gallery-lightbox`.

- [ ] **Step 1: Change gallery tests to exercise rendered Jekyll output**

In `setUpClass`, create `tempfile.TemporaryDirectory()`, save its path as `cls.build_dir`, and run `bundle exec jekyll build --strict_front_matter --destination str(cls.build_dir)`. Assert the rendered title and meta description come from `_data/site.yml`, eight photography buttons render in numeric order, hidden works do not render, the hero uses the featured work, and `coming_soon: true` renders the painting holding state without a painting gallery.

- [ ] **Step 2: Run the gallery tests and confirm hard-coded HTML fails the contract**

Run: `python3 -m unittest tests.test_gallery -v`

Expected: FAIL because `index.html` has no Jekyll front matter and still hard-codes the gallery.

- [ ] **Step 3: Refactor `index.html` into a Liquid renderer**

Add empty front matter and assign visible/sorted photography and painting collections. Select the single visible featured photograph, falling back to the first visible photograph. Render all text from `_data/site.yml`, emit no empty optional contact elements, and choose between the painting holding state and painting gallery using `sections.painting.coming_soon`.

- [ ] **Step 4: Make the grid independent of editor-supplied layout classes**

Replace `.gallery-item--*` selectors with repeating `.gallery-item:nth-child(8n + N)` rules for `N=1..8`. Keep focus, hover, responsive, reduced-motion, and lightbox styling. Update `gallery.js` so the dialog label and counter work for both categories and the script exits safely when no gallery items exist.

- [ ] **Step 5: Verify rendering and browser-independent behavior**

Run: `ruby scripts/validate_content.rb --site _data/site.yml --works _works && python3 -m unittest discover -s tests -v && bundle exec jekyll build --strict_front_matter`

Expected: all Python tests pass and Jekyll exits `0`.

- [ ] **Step 6: Commit the renderer**

```bash
git add index.html assets/css/gallery.css assets/js/gallery.js tests/test_gallery.py
git commit -m "feat: render portfolio from editable content"
```

### Task 3: Add the graphical CMS and visual previews

**Files:**
- Create: `admin/index.html`
- Create: `admin/config.yml`
- Create: `admin/preview.js`
- Create: `admin/preview.css`
- Create: `tests/test_cms_config.py`

**Interfaces:**
- Consumes: Task 1 field names and media paths; Task 2 public CSS classes.
- Produces: Decap collections named `site_settings`, `photography`, and `painting`; preview templates registered under those exact names.

- [ ] **Step 1: Add failing CMS configuration tests**

Assert `backend.name == "git-gateway"`, `backend.branch == "master"`, `publish_mode == "editorial_workflow"`, `locale == "zh_Hans"`, media paths are `assets/images/works` and `/assets/images/works`, the three collection names exist, the two work collections filter the correct category, and `admin/index.html` pins `decap-cms@3.8.3` plus `netlify-identity-widget@1.9.2`.

- [ ] **Step 2: Run the CMS tests and confirm the expected failure**

Run: `python3 -m unittest tests.test_cms_config -v`

Expected: FAIL because the `admin/` files do not exist.

- [ ] **Step 3: Add the CMS shell and configuration**

Configure invite-backed Git Gateway, editorial workflow, `site_url: https://yichuanli98.github.io`, `display_url` to the same URL, `show_preview_links: true`, URL-safe slugs, and JPEG/PNG/WebP media. The singleton settings file exposes every key in `_data/site.yml` and disables deletion. Each work collection exposes all work fields, supplies a hidden fixed `category`, defaults `visible` to true, and uses `order` as an integer.

- [ ] **Step 4: Add custom preview templates**

In `admin/preview.js`, register `SiteSettingsPreview`, `PhotographyPreview`, and `PaintingPreview` with `CMS.registerPreviewTemplate`. Use `entry.getIn(["data", field])` and `getAsset(image)`; render the same hero/card/holding-state class names used by Task 2. Register `/admin/preview.css` with `CMS.registerPreviewStyle`.

- [ ] **Step 5: Verify configuration and local CMS loading**

Run: `python3 -m unittest tests.test_cms_config -v && bundle exec jekyll build --strict_front_matter`

Expected: tests pass and `_site/admin/index.html`, `_site/admin/config.yml`, and preview assets exist.

- [ ] **Step 6: Commit the CMS**

```bash
git add admin tests/test_cms_config.py
git commit -m "feat: add browser portfolio editor"
```

### Task 4: Sanitize and validate uploaded media

**Files:**
- Create: `scripts/sanitize_media.py`
- Create: `requirements-dev.txt`
- Create: `tests/test_media_sanitizer.py`
- Modify: `scripts/validate_content.rb`

**Interfaces:**
- Produces: `sanitize_bytes(data: bytes, suffix: str) -> bytes`, `sanitize_file(path: Path, write: bool) -> bool`, and CLI `python3 scripts/sanitize_media.py (--check|--write) PATH...`.
- Consumes: work `image` paths from Task 1.

- [ ] **Step 1: Add failing format and idempotence tests**

Start from known-valid 1×1 JPEG, PNG, and WebP fixtures, inject JPEG APP1/APP13/COM segments, PNG `eXIf`/`tEXt`/`zTXt`/`iTXt`/`tIME` chunks, and WebP `EXIF`/`XMP ` chunks, then verify before and after with `PIL.Image.verify()`. Assert sanitization removes only prohibited chunks, preserves image payload chunks, updates RIFF size and VP8X flags, and `sanitize_bytes(cleaned) == cleaned`. Assert `--check` exits `1` for dirty fixtures and `0` for cleaned files. Add work fixtures whose `image` is missing or has a `.gif` suffix and assert validator messages contain the work path plus `image`.

- [ ] **Step 2: Run the media tests and confirm the expected failure**

Run: `python3 -m unittest tests.test_media_sanitizer -v`

Expected: FAIL because `scripts.sanitize_media` does not exist.

- [ ] **Step 3: Implement lossless metadata removal**

For JPEG, remove APP1, APP13, and COM segments before SOS while preserving encoded scan data. For PNG, remove the five prohibited ancillary chunk types and preserve all other chunks byte-for-byte. For WebP, remove `EXIF` and `XMP ` chunks, clear their VP8X feature bits, preserve padding, and recalculate the RIFF size.

- [ ] **Step 4: Extend content validation for media references**

Resolve each work image relative to the repository root. Reject missing files, extensions outside `.jpg`, `.jpeg`, `.png`, `.webp`, files over 15 MiB, and bytes for which sanitization would change output. Invoke `python3 scripts/sanitize_media.py --check` once with the unique referenced paths via Ruby `Open3.capture3`; map a failing path back to every referencing work so messages include the work file and `image` field.

- [ ] **Step 5: Verify all formats and current photographs**

Run: `python3 -m pip install -r requirements-dev.txt && python3 -m unittest tests.test_media_sanitizer tests.test_content_model -v && python3 scripts/sanitize_media.py --check assets/images/works`

Expected: all tests pass and the CLI prints `media metadata: clean`.

- [ ] **Step 6: Commit media protection**

```bash
git add requirements-dev.txt scripts/sanitize_media.py scripts/validate_content.rb tests/test_media_sanitizer.py tests/test_content_model.py
git commit -m "feat: sanitize uploaded artwork metadata"
```

### Task 5: Add automated desktop and mobile browser coverage

**Files:**
- Create: `playwright.config.js`
- Create: `tests/gallery.spec.js`
- Modify: `package.json`
- Modify: `.gitignore`
- Create: `package-lock.json`

**Interfaces:**
- Consumes: rendered selectors from Task 2.
- Produces: `npm run test:browser` and Playwright web server at `http://127.0.0.1:4173`.

- [ ] **Step 1: Add browser tests before installing the runner**

Test that desktop loads eight gallery buttons, opens the selected image in the dialog, updates the counter, closes with Escape, and restores focus. Test a `390x844` viewport for zero horizontal overflow and successful image loads. Add a temporary ninth visible work in a copied fixture site and assert all nine buttons are reachable and the final lightbox counter reads `09 / 09`.

- [ ] **Step 2: Run the unavailable browser command**

Run: `npm run test:browser`

Expected: FAIL because the script and Playwright dependency do not exist.

- [ ] **Step 3: Configure Playwright**

Add `@playwright/test: 1.55.0` to `devDependencies`, add `test:browser: playwright test`, and configure Chromium with `webServer.command` set to `bundle exec jekyll serve --host 127.0.0.1 --port 4173 --strict_front_matter`. Remove `package-lock.json` from `.gitignore`, generate and commit the lockfile.

- [ ] **Step 4: Run browser and reduced-motion checks**

Run: `npm ci && npx playwright install chromium && npm run test:browser`

Expected: all desktop, mobile, nine-item, keyboard, and reduced-motion tests pass.

- [ ] **Step 5: Commit browser coverage**

```bash
git add package.json package-lock.json playwright.config.js tests/gallery.spec.js .gitignore
git commit -m "test: cover portfolio browser interactions"
```

### Task 6: Add draft automation, Netlify previews, and operating documentation

**Files:**
- Create: `.github/workflows/cms-draft.yml`
- Create: `.github/workflows/site-quality.yml`
- Create: `netlify.toml`
- Create: `docs/editor-operations.md`
- Delete: `.github/workflows/bad-pr.yml`
- Delete: `.github/workflows/scrape_talks.yml`
- Delete: `.github/workflows/jekyll-build.yml`
- Modify: `tests/test_cms_config.py`

**Interfaces:**
- Consumes: Task 4 CLIs and Task 5 commands.
- Produces: required commit status context `content-quality`, Netlify deploy previews, and owner runbook.

- [ ] **Step 1: Add failing automation-contract tests**

Assert the old template workflows are absent; `cms-draft.yml` triggers on pull requests, grants `contents: write` and `statuses: write`, installs `requirements-dev.txt`, runs sanitizer `--write`, validator, unit tests, Jekyll build, and browser tests, then posts `content-quality` on the resulting head SHA. Assert `site-quality.yml` is read-only and runs on pushes to `master` plus manual dispatch. Assert `netlify.toml` publishes `_site` after `bundle exec jekyll build --strict_front_matter`.

- [ ] **Step 2: Run the contract tests and confirm the expected failure**

Run: `python3 -m unittest tests.test_cms_config -v`

Expected: FAIL because new workflows and `netlify.toml` do not exist and legacy workflows remain.

- [ ] **Step 3: Implement the CMS draft workflow**

Guard write access with `github.event.pull_request.head.repo.full_name == github.repository`. Check out the head branch; set up Ruby 3.2, Python 3, and Node 20; run `bundle install`, `python3 -m pip install -r requirements-dev.txt`, `npm ci`, and `npx playwright install --with-deps chromium`. Run sanitizer `--write`, commit changed media as `Sanitize uploaded media`, and push to the same head ref. Run all validators/tests against the new HEAD and use GitHub’s statuses API to post `content-quality` success or failure on `git rev-parse HEAD`.

- [ ] **Step 4: Implement read-only production quality and Netlify build**

The production workflow checks out code with `contents: read`, sets up Ruby 3.2, Python 3, and Node 20, runs unit tests, Jekyll build, and Playwright. Configure Netlify with `JEKYLL_ENV=production`, publish directory `_site`, and the same strict Jekyll build command.

- [ ] **Step 5: Remove interfering template workflows and write the runbook**

Remove the workflow that closes pull requests with empty bodies because it can close Decap drafts, and remove the academic talk scraper. Document `/admin/` login, draft states, preview link behavior, publishing, failed-check recovery, media errors, rollback, and the fact that preview links are unlisted rather than private.

- [ ] **Step 6: Verify the full local quality command**

Run: `python3 -m pip install -r requirements-dev.txt && ruby scripts/validate_content.rb --site _data/site.yml --works _works && python3 scripts/sanitize_media.py --check assets/images/works && python3 -m unittest discover -s tests -v && bundle exec jekyll build --strict_front_matter && npm run test:browser`

Expected: every command exits `0`.

- [ ] **Step 7: Commit automation and documentation**

```bash
git add .github/workflows netlify.toml docs/editor-operations.md tests/test_cms_config.py
git commit -m "ci: validate and preview CMS drafts"
```

### Task 7: Configure hosted services and prove the complete workflow

**Files:**
- Modify only if verification finds a defect: files owned by Tasks 1-6

**Interfaces:**
- Consumes: `/admin/`, `content-quality`, `netlify.toml`, and `docs/editor-operations.md`.
- Produces: working Netlify Identity/Git Gateway, deploy previews, protected `master`, and a verified production publish.

- [ ] **Step 1: Push the implementation branch and connect Netlify**

Create a Netlify site from `YichuanLi98/yichuanli98.github.io`, confirm the build command and `_site` publish directory came from `netlify.toml`, and verify a branch deploy returns HTTP 200. Keep `https://yichuanli98.github.io/` as the canonical production URL.

- [ ] **Step 2: Configure owner-only authentication**

Enable Netlify Identity, set registration to invite-only, enable only the GitHub external provider, enable Git Gateway for this repository, and invite the owner’s login email interactively without writing it to the repository. Verify an incognito, uninvited session cannot edit.

- [ ] **Step 3: Protect `master` after observing real status names**

Create a CMS draft, set `CMS_DRAFT_SHA="$(gh pr view --json headRefOid --jq .headRefOid)"`, then query `gh api "repos/YichuanLi98/yichuanli98.github.io/commits/$CMS_DRAFT_SHA/status"` and capture the exact Netlify deploy-preview context. Configure branch protection to require that context plus `content-quality`, require branches to be up to date, and disallow force pushes and deletion.

- [ ] **Step 4: Exercise draft, preview, validation, and publish**

Through `/admin/`, change the footer back-to-top label from `Back to top ↑` to `Back to top`, save as a draft, and verify `master` plus the live site remain unchanged. Open the Netlify preview and verify the changed label, responsive gallery, and lightbox. Publish only after required checks pass; verify GitHub Pages serves the changed label, then restore `Back to top ↑` through a second reviewed draft.

- [ ] **Step 5: Run final repository and remote verification**

Run: `git status --short --branch`, the complete Task 6 quality command, `gh pr list --state open`, `gh run list --limit 10`, and `curl -fsS https://yichuanli98.github.io/`.

Expected: clean branch, all local checks pass, no abandoned CMS pull request remains, the latest required workflows succeed, and production returns HTTP 200 with the restored footer label.

- [ ] **Step 6: Record final evidence**

Add the verified Netlify site identifier, exact required status names, test commands, and rollback confirmation to `docs/editor-operations.md` without storing secrets; commit as `docs: record editor deployment verification`.
