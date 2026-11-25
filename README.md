# PortWatch registry probe

Independent read-only verification of the public `portwatch-vi.xyz/data/tracker.json` and its GitHub source. This repository is not affiliated with PortWatch; it does not change the upstream project, trigger its workflows or submit editorial decisions.

GitHub Actions runs at minute 15 of each UTC hour and publishes compact results at `evidence/latest.json`. The first push of the workflow to `main` also starts a run; a manual run is available under Actions. Scheduled runs may be delayed by GitHub.

## Deploy

Unpack the ZIP into a new directory, then in that directory run:

```powershell
gh auth status
gh auth setup-git
git init -b main
git add .
git commit -m "Add independent PortWatch verification probe"
gh repo create tudorek12345/portwatch-registry-probe --public --source=. --remote=origin --push
```

Use your own authenticated GitHub account. If Git asks for a commit identity, configure your own name and GitHub noreply address locally. GitHub Actions must be enabled and allowed to write repository contents. No Cloudflare credentials or personal access token are required by the workflow.

## Interpret evidence

- `live.ok`: HTTP 200, intended final URL, JSON content type and valid registry schema.
- `github_source.ok`: successfully fetched and validated public source registry.
- `byte_identical`: raw SHA256 hashes match; null if either fetch failed.
- `matches_current_source`: parsed content matches after normalizing the URL rewrite used by PortWatch's deployment workflow. False when data differs or either fetch fails. A mismatch can be a transient deployment race.
- `live_matches` / `github_source_matches`: matching records in monitored categories, including flag reasons when present. Null means retrieval failed; an empty list means no matches in the retrieved snapshot.
- `checked_at` and `runner.run_url`: when and where the observation was made.

No evidence is shipped in this package. The first successful workflow execution creates the JSON evidence file. A failed HTTP fetch still produces an observation and never implies a project is absent. The report contains only public registry metadata and matching records; it does not publish credentials or the complete registry.

## Local tests

`python -m unittest -v test_probe` uses mocked HTTP responses. `python probe.py` performs real public HTTPS requests and generates local evidence. For automated monitoring, use the GitHub-hosted result, not the local test.
