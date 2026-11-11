# TechMachine

Repository management for the GetTechAPI organisation. Where
[TechEngine](https://github.com/GetTechAPI/TechEngine) processes the data,
TechMachine looks after the repositories that hold it. It does two things:
a health check over every repository, and a scaffolder for new satellite
data repositories.

## The organisation's repositories

| Repository | What it is |
| --- | --- |
| [TechAPI](https://github.com/GetTechAPI/TechAPI) | The dataset and the site |
| [TechEngine](https://github.com/GetTechAPI/TechEngine) | The engine that processes the data; TechAPI pins it as a submodule |
| [game-catalog](https://github.com/GetTechAPI/game-catalog) | Satellite data repository: games |
| [cpu-engineering-samples](https://github.com/GetTechAPI/cpu-engineering-samples) | Satellite data repository: CPU engineering samples |
| [.github](https://github.com/GetTechAPI/.github) | The organisation profile and shared community files |
| TechMachine | This repository: health check and satellite scaffolder |

## Health check

`machine/health.py` runs when a person starts it: the `health` workflow's
*Run workflow* button, or locally. It reads [`machine/repos.json`](machine/repos.json)
and reports three kinds of problem.

1. **The latest completed run of each active workflow, per tracked branch.**
   Anything other than `success`, `skipped` or `neutral` is reported,
   `cancelled` and `timed_out` included. That is deliberate: a job killed at
   GitHub's six-hour limit reports itself as *cancelled*, and several
   automations here failed that way for days without anyone noticing. Each
   workflow is queried separately rather than scanning "the last N runs",
   because weekly jobs scroll out of any fixed window behind the daily ones,
   and the weekly jobs are the ones that go quiet. Disabled workflows are
   skipped, and so is GitHub's own *Dependabot Updates* workflow in a
   repository that no longer has a `.github/dependabot.yml` (or `.yaml`).
2. **Secrets.** It reads each active workflow file on each tracked branch and
   reports any that uses a secret other than `GITHUB_TOKEN` or the
   repository's `allowed_secrets`. Automation here must act as
   `github-actions[bot]`, never as a person: workflows running under a
   personal token are how a maintainer's account got suspended. The one
   allowed secret is `TECHENGINEBOT_TOKEN`, which the label-triggered final
   check uses to post its comment. Disabling a workflow in the Actions
   settings clears its finding.
3. **Endpoints.** It fetches each public URL listed under `endpoints` and
   reports one that is unreachable, is not JSON, or lacks its `expect` field.
   These are the files the TechAPI homepage depends on.

A repository that cannot be read is reported too, rather than passed over.

It only reads. The report goes to stdout and the run's step summary; it
writes nothing to GitHub, mentions nobody, and runs on no schedule. An
account here was suspended over automation, and a report nobody asked for is
how that starts. The run itself always ends green: the report is the output.

```bash
python -m machine.health            # print the report (GITHUB_TOKEN raises the rate limit)
python -m pytest -q
```

Adding a repository or endpoint is one entry in `machine/repos.json`: a
`name`, the `branches` to watch and, where the final check runs,
`"allowed_secrets": ["TECHENGINEBOT_TOKEN"]`. A repository with no workflows
(the `.github` profile repository) is listed with its branch only.

## Final check

Adding the `final-check` label to a pull request asks
[TechEngineBot](https://github.com/TechEngineBot) for a last look. The check
job runs the tests (including a generated satellite repository), validates
`repos.json`, and checks syntax and that every action is GitHub-owned and
pinned by full commit SHA, both in this repository's workflows and in the
ones the template generates (`tests/test_pinned_actions.py`). TechEngineBot
then leaves **one** comment with the verdict; adding the label again edits it.

The check job runs the PR's code with no secrets and a read-only token. Only
the comment job sees `TECHENGINEBOT_TOKEN`, and it posts nothing unless that is
a fine-grained token belonging to TechEngineBot. This is the only thing the
bot account does here: it speaks when a person asks, once per PR. Same design
as TechAPI's final check.

## Satellite repositories

Categories that do not belong in TechAPI live in their own repository
([game-catalog](https://github.com/GetTechAPI/game-catalog),
[cpu-engineering-samples](https://github.com/GetTechAPI/cpu-engineering-samples)).
The split criterion is identity, not size: software and websites are tech
data and stay in TechAPI.

`machine/new_satellite.py` writes a new one from
[`machine/satellite_template/`](machine/satellite_template):

```bash
python -m machine.new_satellite --repo game-catalog --category game \
    --title "Game catalog" --plural games --date-field release_date \
    --range rating:0:5 --range metacritic:0:100 --out ../game-catalog
```

### What it generates

```
.github/CODEOWNERS                    # * @GetTechAPI/maintainers
.github/pull_request_template.md
.github/workflows/validate-data.yml   # validator + tests on PRs and pushes to develop/main
.github/workflows/deploy-pages.yml    # builds and publishes the site from main
.github/workflows/final-check.yml     # the label-triggered check and TechEngineBot's comment
.gitignore
DATA_LICENSE.md                       # CC BY-SA 4.0 for the records
LICENSE                               # MIT for the code
README.md
app/__init__.py
app/validate.py                       # required fields, slug, dates, ranges, duplicates
pyproject.toml
site/.nojekyll
site/build.py                         # summary.json + history.json, never a listing of every record
site/index.html
tests/test_validate.py
data/<category>/                      # empty; records go in <bucket>/<slug>.json
```

The workflows follow the organisation's rules: GitHub-owned actions pinned
by full commit SHA, least-privilege `permissions:`, no schedules, nothing
that opens pull requests or issues, and no secret except
`TECHENGINEBOT_TOKEN` in the final check's comment job. There are no issue
templates; those are shared from the `.github` repository.

The tests generate a repository, compare its tree with the list above, and
run *its* test suite and validator, so a template change that breaks or
reshapes generated repositories fails here.

### Creating a satellite

The scaffolder only writes files. Everything else changes the organisation,
so it is left to a person; the same list is printed after generating.

1. Generate the files with the command above.
2. Create the repository: `gh repo create GetTechAPI/<repo> --public`.
3. Push the scaffold to `develop`, then `develop` to `main`.
4. Turn Pages on with the workflow as its source:
   `gh api -X POST repos/GetTechAPI/<repo>/pages -f build_type=workflow`.
5. Add `main` to the Pages environment's deployment branches:
   `gh api -X POST repos/GetTechAPI/<repo>/environments/github-pages/deployment-branch-policies -f name=main`.
   Without it every deploy fails and leaves no log.
6. Add the repository to `machine/repos.json` here, with
   `"allowed_secrets": ["TECHENGINEBOT_TOKEN"]`, and its `summary.json` URL
   to `endpoints`.
7. Add it to `SATELLITES` in TechAPI's `site/src/scripts/techapi.js` so the
   homepage counts it.
8. For the final check, create the `final-check` label and set the
   `TECHENGINEBOT_TOKEN` secret to a fine-grained token of TechEngineBot with
   *Pull requests: read and write* on that repository only.

## Branching

`develop` is the default branch; `main` is the released state. Pull requests
target `develop`.

## License

MIT ([LICENSE](LICENSE)).
