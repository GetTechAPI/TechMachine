# TechMachine

Repository management for the GetTechAPI organisation. Where
[TechEngine](https://github.com/GetTechAPI/TechEngine) processes the data,
TechMachine looks after the repositories that hold it.

## Health check

`machine/health.py` runs daily and keeps one issue, **Org health report**,
up to date. For every repository in [`machine/repos.json`](machine/repos.json)
it reads the newest completed run of each active workflow on each tracked
branch, and it fetches the public endpoints the TechAPI homepage depends on.

Anything other than `success`, `skipped` or `neutral` is reported —
`cancelled` and `timed_out` included. That is deliberate: a job killed at
GitHub's six-hour limit reports itself as *cancelled*, and several automations
here failed that way for days without anyone noticing.

It queries each workflow separately rather than scanning "the last N runs",
because weekly jobs scroll out of any fixed window behind the daily ones — and
the weekly jobs are the ones that go quiet.

```bash
python -m machine.health            # print the report
python -m machine.health --issue    # also update the issue (needs GITHUB_TOKEN)
python -m pytest -q
```

Adding a repository or endpoint is one entry in `machine/repos.json`.

## Branching

`develop` is the default branch; `main` is the released state. Pull requests
target `develop`.

## License

MIT ([LICENSE](LICENSE)).
