# Local quickstart

```bash
uv sync --all-extras
uv run business-change-impact-agent validate
uv run business-change-impact-agent analyse --output artifacts/analysis.json --db artifacts/impact-room.sqlite3 --run-id atlasbridge-001
uv run business-change-impact-agent review-init --db artifacts/impact-room.sqlite3 --analysis artifacts/analysis.json --run-id atlasbridge-001
```

Use the returned digest and one-time nonce in the `review` command. Then export all formats:

```bash
uv run business-change-impact-agent export --db artifacts/impact-room.sqlite3 --run-id atlasbridge-001 --output-dir artifacts/exports
uv run business-change-impact-agent verify-ledger --db artifacts/impact-room.sqlite3
```

The fully automated synthetic demonstration is:

```bash
uv run business-change-impact-agent demo --workspace artifacts/demo
```
