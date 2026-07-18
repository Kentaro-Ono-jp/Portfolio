# End-to-end tests

This directory will contain tests that verify complete user-visible workflows
against the assembled system.

Playwright will drive the first complete browser workflow using a synthetic
single-page invoice PDF. It must verify upload, asynchronous state progression,
the terminal `invoice` result, confidence, model version, and invalid-file
handling against the assembled Compose system.
