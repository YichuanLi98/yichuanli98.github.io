# Visual Website Editor Design

**Date:** 2026-09-25

**Site owner:** Yichuan Li (`YichuanLi98`)

**Repository:** `YichuanLi98/yichuanli98.github.io`

## Purpose

Add a browser-based graphical editor to the existing photography and painting portfolio. The owner must be able to sign in, edit all site content, upload and arrange works, save drafts, preview them, and publish only after review without editing HTML or using Git directly.

The GitHub repository remains the source of truth. The published site continues to build from `master` with GitHub Pages, while Netlify supplies authentication and pull-request deploy previews.

## Confirmed Requirements

- Only the GitHub account `YichuanLi98` may edit the site.
- The editor must cover site copy, metadata, navigation, contact links, photography, and painting.
- Work entries can be created, updated, hidden, reordered, and deleted.
- Image uploads support JPEG, PNG, and WebP.
- Drafts do not change the live site.
- A complete preview is available before publishing.
- Preview links do not require authentication; anyone holding a link can view them.
- Publishing requires successful content, build, accessibility, and media checks.
- Uploaded images must not retain EXIF or other private metadata.
- The painting section keeps a configurable “coming soon” state.
- The existing visual direction, responsive gallery, and lightbox are preserved.

## Non-Goals

- The CMS will not edit CSS, JavaScript, Liquid templates, or GitHub/Netlify configuration.
- The first version will not support multiple editors, role management, scheduled publishing, comments, analytics, or multilingual content.
- It will not introduce a database or move canonical content outside Git.
- Draft preview URLs are unlisted, not private or password protected.

## Architecture

### Canonical content and production

GitHub remains the canonical store. `master` contains only published content and is the GitHub Pages production source. The current production URL is `https://yichuanli98.github.io/`.

### Browser editor

Decap CMS is served as static files at `/admin/`:

- `admin/index.html` loads a pinned stable Decap CMS release and the Netlify Identity client.
- `admin/config.yml` declares collections, fields, media folders, preview paths, and editorial workflow.
- `admin/preview.js` registers preview templates for site settings and works.
- `admin/preview.css` reuses the portfolio’s visual tokens inside the preview pane.

The CMS interface and field labels use Simplified Chinese. The public content remains freely editable in English or any text the owner chooses.

### Authentication and authorization

Netlify Identity is configured as invite-only with GitHub as the external login provider. Only the owner’s invited identity is created. Netlify Git Gateway writes to the GitHub repository on behalf of that authenticated identity.

The `/admin/` shell is publicly downloadable because it is static, but repository reads and all writes require authentication. The repository and Git Gateway permissions remain scoped to this one site.

### Draft and publish workflow

Decap CMS uses `publish_mode: editorial_workflow`.

1. The owner edits content in `/admin/` and sees an immediate CMS preview.
2. Saving creates or updates a CMS branch and GitHub pull request.
3. Netlify builds the pull request and reports an unlisted deploy-preview URL.
4. GitHub Actions validates and sanitizes the proposed content.
5. The CMS exposes publish only when the draft is ready; protected-branch checks prevent an invalid merge.
6. Publishing merges the pull request into `master` and removes the draft branch.
7. GitHub Pages rebuilds the production site from `master`.

Netlify also builds `master` at its own secondary URL because it is connected to the repository, but that URL is not canonical and is marked `noindex` where possible. GitHub Pages remains the public production host.

## Content Model

### Site settings

`_data/site.yml` contains all owner-editable global content:

- Owner name and signature
- Browser title and SEO description
- Hero eyebrow, heading, introduction, and selected hero work
- Navigation labels
- Photography section title and introduction
- Painting section title, introduction, and `coming_soon` switch
- Featured photography selection and complete photography/painting ordering lists
- “Coming soon” message
- Footer text
- Email and supported social links

The file is a singleton CMS entry and cannot be renamed or deleted.

### Works

Each work is stored as one Markdown file under `_works/`. The body is optional; structured front matter carries the fields needed by the gallery:

- `title`: internal and public title
- `category`: `photography` or `painting`
- `image`: repository-hosted media path
- `alt`: required image description
- `description`: optional public caption
- `location`: optional location
- `date`: optional creation date
- `visible`: whether a published work appears on the public site

The filename supplies a stable slug. Entries may be created, renamed, or deleted through the CMS. The singleton site-settings entry selects the featured photography slug and stores each category's complete order, so a reorder or hero switch is one atomic editorial-workflow draft rather than several independent work-entry pull requests. Validation rejects duplicate slugs and requires the selected hero to resolve to a visible photograph.

### Media

CMS uploads are stored under `assets/images/works/`. Only `.jpg`, `.jpeg`, `.png`, and `.webp` files are accepted. Filenames are normalized to URL-safe slugs.

A repository script removes EXIF, IPTC, XMP, comments, and similar metadata without changing the visible composition. A pull-request workflow applies the sanitizer to new or changed media on the CMS branch, commits sanitized bytes back to that branch when needed, and then runs validation against the sanitized result.

The workflow also enforces a configurable maximum file size. It reports actionable errors when an image format is unsupported, an asset is missing, or a required alt description is empty.

## Rendering

`index.html` becomes a Jekyll/Liquid template driven by `_data/site.yml` and `site.works`.

- Visible works are grouped by category and rendered in the slug order stored in site settings; newly published works not yet listed are appended deterministically.
- The hero uses the visible photograph selected in site settings, with a safe fallback to the first visible photograph.
- The painting “coming soon” presentation remains visible while `coming_soon` is true.
- When `coming_soon` is false, visible paintings render as a gallery using the same lightbox behavior as photography.
- The gallery layout remains responsive and does not require editors to choose CSS layout classes.
- Missing optional text produces no empty visual element.

Legacy template collections remain excluded from production. The new `_works` collection is readable by Liquid but does not generate individual public work pages.

## Editor Experience

The CMS navigation contains:

1. Workflow
2. Website settings
3. Photography
4. Painting
5. Media library

Work forms show structured fields beside a visual preview that uses the current gallery styling. The collection list exposes title, category, date, and visibility so the owner can understand the gallery without opening every entry.

Ordering and featured selection use relation widgets inside the singleton site-settings entry. Their changes therefore share one Git commit and one preview. CI rejects duplicate order-list slugs or a hero selection that is missing, hidden, or not photography.

## Validation and Failure Handling

Pull requests run these checks:

- Parse all YAML/front matter.
- Verify the site-settings schema and required fields.
- Verify work category and visibility plus the site-level hero selection and ordering rules.
- Verify that every referenced image exists and has an allowed media type.
- Verify required alt text.
- Sanitize new media and verify that private metadata is absent.
- Build the Jekyll site without unsupported plugins.
- Check rendered links and image responses.
- Run browser smoke tests for desktop and mobile gallery behavior, keyboard lightbox controls, and the painting state.

If sanitization changes a file, the workflow commits the cleaned version to the draft branch before the final checks. If any check fails, the pull request remains open and production stays unchanged. The check output identifies the affected content file and field where possible.

If Netlify preview generation fails, the draft remains editable and publish is blocked by its required status. If GitHub Pages deployment fails after a merge, the prior deployment remains available while the failed build is diagnosed. Git history permits reverting a published change.

## Security and Privacy

- Netlify Identity registration is invite-only.
- Only the owner identity is invited.
- GitHub is the only enabled external identity provider.
- The Git Gateway connection is scoped to `YichuanLi98/yichuanli98.github.io`.
- No GitHub token, OAuth secret, or Netlify credential is committed to the repository.
- The admin page uses a pinned CMS version rather than an unbounded CDN version.
- The admin page and Netlify preview environment are marked `noindex`.
- Draft previews are deliberately unlisted but are not treated as confidential.
- Image metadata removal happens before publishing.

## Repository Changes

Expected implementation areas:

- Add `admin/index.html`, `admin/config.yml`, `admin/preview.js`, and `admin/preview.css`.
- Add `_data/site.yml` and migrate current copy into it.
- Add `_works/` entries for the eight existing photographs.
- Update `_config.yml` with the non-output `works` collection and production exclusions.
- Refactor `index.html` to use Liquid data and render both categories.
- Adapt `assets/css/gallery.css` and `assets/js/gallery.js` for data-driven entries.
- Add `netlify.toml` for Jekyll builds and deploy previews.
- Add media sanitization and content-validation scripts.
- Add GitHub Actions for media sanitation, validation, build, and browser smoke tests.
- Expand `tests/test_gallery.py` and add focused content-schema tests.

Netlify Identity, Git Gateway, the GitHub login provider, and branch protection require account-level configuration outside the repository. Those steps are part of rollout but are never represented as committed secrets.

## Rollout

1. Refactor content and rendering locally while preserving the current public output.
2. Add CMS configuration and custom previews; exercise them with Decap’s local backend for form behavior only.
3. Add validation, sanitation, build, and browser tests.
4. Connect the repository to Netlify and confirm deploy previews.
5. Enable invite-only Netlify Identity, GitHub login, and Git Gateway; invite only the owner.
6. Protect `master` with the required validation and Netlify preview statuses.
7. Test the complete draft-to-publish flow with a harmless text change.
8. Confirm both the published GitHub Pages site and rollback path.

## Acceptance Criteria

- `YichuanLi98` can sign in through GitHub and reach the CMS; an uninvited account cannot edit.
- Every current public text value and link has a graphical field.
- The owner can create, update, hide, reorder, and delete photography and painting entries.
- Saving a draft does not modify `master` or the live GitHub Pages site.
- A draft produces both an in-editor preview and a complete Netlify deploy preview.
- Invalid content or media cannot be merged.
- Publishing merges the reviewed draft and updates the GitHub Pages site.
- New public images contain no prohibited metadata.
- Existing desktop and mobile visual behavior remains intact.
- The painting section can switch cleanly between “coming soon” and a live gallery.

## References

- Decap CMS editorial workflow: https://decapcms.org/docs/editorial-workflows/
- Decap CMS Git Gateway setup: https://decapcms.org/docs/choosing-a-backend/
- Decap CMS deploy previews: https://decapcms.org/docs/deploy-preview-links/
- Decap CMS custom previews: https://decapcms.org/docs/customization/
- Decap CMS configuration: https://decapcms.org/docs/configuration-options/
