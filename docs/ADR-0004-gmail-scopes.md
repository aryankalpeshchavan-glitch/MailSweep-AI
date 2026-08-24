# ADR-0004: Gmail API scope selection

**Status:** Accepted · **Date:** Milestone 0

## Decision

MailSweep requests exactly four OAuth scopes:

| Scope | Why |
|---|---|
| `openid` | Identify the user after sign-in. |
| `email` | Read the verified Google account address to bind the MailSweep user record. |
| `profile` | Display name/avatar for the future dashboard header. |
| `https://www.googleapis.com/auth/gmail.modify` | The actual work: list/read **metadata**, read labels, and move messages to Trash (`users.messages.trash`). |

## Alternatives considered

### ❌ `gmail.readonly` (+ nothing else)
Cannot trash messages. Useless alone.

### ❌ `https://mail.google.com/` (full access)
Grants permanent deletion and full body reads. Massively over-privileged;
rejected on principle even though it "works".

### ⚠️ Split: `gmail.metadata` + `gmail.modify`
Tempting because `gmail.metadata` *sounds* narrower, but Gmail's effective
access is the **union** of granted scopes: once `gmail.modify` is present,
body reads are already technically possible, so adding `gmail.metadata` adds
zero restriction while adding consent-screen noise. Rejected as redundant.
(If Google ever ships a metadata-write-only or trash-only scope, we migrate.)

## The honest caveat (documented, not hidden)

`gmail.modify` is the narrowest published scope that can perform
`messages.trash`, but it also permits reading bodies and editing labels.
MailSweep's defense against over-read is therefore **behavioral, not
scope-based**: the code path only ever calls `messages.list` /
`messages.get(format="metadata"|"minimal")`, `labels.list`, and
`messages.trash`. There is no code path that requests a body format, and tests
assert the fake client never receives one. This is stated in README/SECURITY
rather than claimed away by a narrower-looking scope list.
