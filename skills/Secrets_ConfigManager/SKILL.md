---
name: Secrets_ConfigManager
description: Manage `.env` and secrets safely across local and VM without leaking credentials into git or logs.
---

## When To Use
Use whenever adding/changing API keys, OAuth tokens, or passwords.

## Inputs
- `.env` (local/VM only)
- `.env.example` (documented contract)

## Preconditions
- `.env` is gitignored

## Steps
1. Keep secrets only in `.env` on local/VM.
1. Document required keys in `.env.example` with safe placeholders.
1. Ensure scripts do not echo env values.

## Acceptance Criteria
- No secrets committed.
- CI/logs do not print secrets.

## Verification
- `git status --porcelain=v1`
- `rg -n \"AIza\" -S . || true`

## Failure Modes And Fallbacks
- Secret accidentally committed: rotate the credential immediately.

