# Contributing

Issues and pull requests are welcome.

## Before Opening A PR

1. Open an issue first for substantial changes so the scope is clear.
2. Keep changes focused. Avoid mixing refactors, demo behavior changes, and documentation cleanup in one PR.
3. Do not commit secrets, `.env` files, local vector stores, generated decks, or screenshots unless the change explicitly requires them.

## Local Validation

Run the smallest relevant checks for the files you changed:

```bash
make test
make test-hub
make lint
```

For demo-specific changes, run the matching target such as `make test-demo-03`.

## Style

- Prefer small, readable changes over broad rewrites.
- Keep demo fixtures synthetic. Do not replace fake credentials or attack samples with real ones.
- Update top-level docs when repo behavior, setup flow, or demo inventory changes.

## Pull Request Notes

Include:

- what changed
- why it changed
- how you validated it
- any demo, Azure, or local-model prerequisites needed to review it
