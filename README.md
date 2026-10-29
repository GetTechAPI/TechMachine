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

It also reads each active workflow file and reports any that uses a secret
other than `GITHUB_TOKEN`. Automation here must act as `github-actions[bot]`,
never as a person: workflows running under a personal token are how a
maintainer's account got suspended. Disabling the workflow in the Actions
settings clears the finding; a non-token secret a repository genuinely needs
goes in that repository's `allowed_secrets` in `repos.json`.

```bash
python -m machine.health            # print the report
python -m machine.health --issue    # also update the issue (needs GITHUB_TOKEN)
python -m pytest -q
```

Adding a repository or endpoint is one entry in `machine/repos.json`.

When the set of problems changes, the check comments on the issue and
@-mentions `notify` from that file — editing an issue body notifies nobody.
It stays quiet when the same failure recurs (the fingerprint is
workflow + result, not the run link) and never pings for an all-clear.

## Final check

[TechEngineBot](https://github.com/TechEngineBot) gives important pull
requests a last look before merge. A person asks for it by adding the
`final-check` label; the bot then posts **one** comment (later pushes edit it,
never add another) and a `final-check` commit status that branch protection
can require.

It blocks a draft, a merge conflict, a PR into `main` that is not a release
from `develop` or a `hotfix/`, any other check that failed or was cancelled,
a changed workflow that uses a personal token, and a commit no other check
ran on at all. It waits up to 30 minutes for running checks before judging.
It never checks out or runs the PR's code.

The account was suspended once for spam, so this is its only job: it speaks
only when asked, and only once per PR.

Another repository opts in with `.github/workflows/final-check.yml`:

```yaml
name: final-check
on:
  pull_request_target:
    types: [labeled, synchronize, ready_for_review]
jobs:
  final-check:
    uses: GetTechAPI/TechMachine/.github/workflows/final-check.yml@main
    secrets: inherit
```

It needs a `final-check` label in that repository and the
`TECHENGINEBOT_TOKEN` secret: a fine-grained token of the TechEngineBot
account with read access to contents and checks, and write access to pull
requests (comments) and commit statuses — best as an organisation secret.

```bash
python -m machine.final_check --repo GetTechAPI/TechAPI --pr 367   # print the verdict only
```

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
