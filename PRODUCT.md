# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary users are a household of learners: the operator plus a small set of family, partner, or friends. Accounts are created for them; they sign in to study traditional Chinese vocabulary. The operator also uses Django admin to provision accounts and enter words and decks.

There is no public or self-serve audience.

## Product Purpose

juzi is a study app for practicing traditional Chinese words. A learner signs in, works through vocabulary in three quiz directions (pinyin → English, English → Chinese, Chinese → English), and sees due words come back on a schedule.

Success is that household learners can keep a reliable practice loop: the right words return when they are due, in the direction being practiced.

## Positioning

juzi is opinionated directional practice for traditional Chinese vocabulary — not a general SRS toolbox and not a character, sentence, or audio trainer. Neighboring products can do flashcards; they cannot truthfully claim this product's job is only those three directions, with per-word due dates, for a private household.

## Operating Context

- Learners use the same-origin web app (Django serving the Preact SPA) in a browser or as an installable online-first PWA. Session cookies are the auth mechanism. Study requires network; the service worker only caches the app shell.
- The operator creates study accounts and vocabulary in Django admin. There is no in-app registration or password reset.
- Study content is entered as words (traditional Chinese, tone-marked pinyin, basic English gloss) grouped into named decks (`Category` in the data model).
- Production is a single DigitalOcean droplet (documented around `juzi.sfreund.tools`). Local work is Django on `:8000` with optional Vite HMR on `:5173`.

Current shipped slice: sign-in, deck picker, study loop, and installable PWA shell.

## Capabilities and Constraints

Confirmed:

- Product name is **juzi**. The local folder name `chengzi` is not the brand.
- Vocabulary is traditional Chinese, with tone-marked pinyin and a basic English gloss.
- Practice modes: `pinyin_to_en`, `en_to_zh`, `zh_to_en`.
- Per-user, per-word progress (`UserWord`: `easy_streak`, `easy_count`, `due_on`, `last_practiced_at`). Quiz mode for a session card is chosen randomly among modes unlocked from `easy_count` milestones.
- Scheduling: hard resets streak and sets due today; easy advances streak/count and schedules by the streak ladder in settings. Session = due words in the chosen category × difficulty bands, one card per word.
- Accounts are admin-provisioned (email + password, stored lowercase). No public registration.
- App chrome stays in English. Chinese appears as study content, not UI language.
- This is a web product, not a native iOS or Android app.

Undecided (do not invent):

- Whether a learner can see or edit their own progress beyond practicing.

## Brand Commitments

- Name: **juzi**, written lowercase in current UI chrome.
- Voice in shipped copy is short, direct English (“Sign in to continue studying.”). Placeholder engineering lines (“next slice”, “deck-picker API lands”) are not brand voice.

## Evidence on Hand

- Brand mark: tangerine icon — `frontend/public/favicon.svg`, PWA PNGs (`pwa-192.png`, `pwa-512.png`, `pwa-maskable-512.png`, `apple-touch-icon.png`), and `site.webmanifest`.
- No vocabulary seed, fixtures, audio, testimonials, or case studies.
- Test-only sample word: 字 / zì / character (`api/tests/test_auth.py`).
- Future work must not fabricate decks, learner quotes, usage stats, or curriculum claims.

## Product Principles

1. Practice is directional: each session is one of the three word quizzes, not a generic card flip.
2. Due words come back; progress is per learner, per word.
3. The household is closed: accounts and content are operator-provisioned.
4. Study material is traditional Chinese with pinyin and a basic English gloss — nothing else is required to start.
5. Ship the practice loop before adjacent study types (sentences, characters, audio).
