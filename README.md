# TechMachine

Repository management for the GetTechAPI organisation. Where
[TechEngine](https://github.com/GetTechAPI/TechEngine) processes the data,
TechMachine looks after the repositories that hold it.

## Health check

`machine/health.py` runs when a person starts it — the `health` workflow's
*Run workflow* button, or locally. For every repository in [`machine/repos.json`](machine/repos.json)
it reads the newest completed run of each active workflow on each tracked
branch, and it fetches the public endpoints the TechAPI homepage depends on.

Anything other than `success`, `skipped` or `neutral` is reported —
`cancelled` and `timed_out` included. That is deliberate: a job killed at
GitHub's six-hour limit reports itself as *cancelled*, and several automations
here failed that way for days without anyone noticing.

It queries each workflow separately rather than scanning "the last N runs",
because weekly jobs scroll out of any fixed window behind the daily ones — and
the weekly jobs are the ones that go quiet.

It also reads each active workflow file and reports any that uses a secret
other than `GITHUB_TOKEN`. Automation here must act as `github-actions[bot]`,
never as a person: workflows running under a personal token are how a
maintainer's account got suspended. Disabling the workflow in the Actions
settings clears the finding; a non-token secret a repository genuinely needs
goes in that repository's `allowed_secrets` in `repos.json` — TechAPI's
label-triggered final check is the one place TechEngineBot's token is allowed.

It only reads. The report goes to stdout and the run's step summary; it
writes nothing to GitHub, mentions nobody, and runs on no schedule — an
account here was suspended over automation, and a report nobody asked for is
how that starts.

```bash
python -m machine.health            # print the report (GITHUB_TOKEN raises the rate limit)
python -m pytest -q
```

Adding a repository or endpoint is one entry in `machine/repos.json`.

## Satellite repositories

Categories that do not belong in TechAPI live in their own repository (games:
[game-catalog](https://github.com/GetTechAPI/game-catalog)). The split
criterion is identity, not size — software and websites are tech data and
stay in TechAPI.

`machine/new_satellite.py` writes a new one from the layout game-catalog
proved out: a streaming validator, a site build that publishes
`summary.json` + `history.json` (never a listing of every record), CI, and
licences.

```bash
python -m machine.new_satellite --repo game-catalog --category game     --title "Game catalog" --plural games --date-field release_date     --range rating:0:5 --range metacritic:0:100 --out ../game-catalog
```

It only writes files. Creating the repository changes the organisation, so
that is left to a person; the remaining steps are printed at the end,
including adding `main` to the Pages environment's deployment branches —
without it every deploy fails and leaves no log.

The tests generate a repository and run *its* test suite and validator, so a
template change that breaks generated repos fails here.

## Branching

`develop` is the default branch; `main` is the released state. Pull requests
target `develop`.

## License

MIT ([LICENSE](LICENSE)).
