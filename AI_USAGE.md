# AI Usage Disclosure

## Tools used

GitHub Copilot using the Copilot SDK in VS Code.

## What I used them for

I used it to research official Python and SQLite documentation, break the
assignment into reviewable stages, implement the SQLite pipeline, and draft
focused tests and documentation.

## What I wrote or decided myself

The selected scope, SQLite design, append-only event model, HMAC lookup and
AES-GCM storage approach, merge behavior, orphan relinking behavior, report
formatting, and edge-case decisions were reviewed as part of the implementation.

## Where the AI was wrong or unhelpful

An initial lead-merge implementation applied defaults before merging. That would
allow an invalid optional value in a duplicate row to overwrite an earlier valid
value with the default. A focused test exposed the issue, so the implementation
was changed to apply defaults only after the merge.

## How I verified AI-generated code

I ran the focused and full pytest suites, compiled the Python modules, checked
whitespace, initialized SQLite from the schema, and ran both generated drops
with a fresh seed. I also re-ingested a completed drop and verified that it was
skipped without changing the database.
