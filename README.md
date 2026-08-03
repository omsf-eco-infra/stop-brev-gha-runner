# stop-brev-gha-runner

Remove ephemeral, repository-scoped GitHub Actions runners from
[NVIDIA Brev](https://docs.nvidia.com/brev/llms.txt). The action removes each
GitHub runner registration before permanently deleting its Brev instance with
`brev delete` through the [`gha-runner`](https://gha-runner.readthedocs.io/)
teardown lifecycle.

## Setup

1. Create a Brev CLI token from the
   [Brev CLI settings page](https://brev.nvidia.com/settings/cli).
2. Add it as the repository secret `BREV_TOKEN`.
3. Add a GitHub token able to manage repository self-hosted runners as
   `GH_PAT`.

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `instance_mapping` | yes | | The start action's `mapping` output: a JSON object mapping Brev instance names to runner labels. |
| `brev_org` | no | token's active org | Brev organization name. Must match the start action when set. |
| `repo` | no | current repository | Repository containing the runner registrations. |

The action requires non-empty `BREV_TOKEN` and `GH_PAT` environment variables.

## Usage

Cleanup uses `if: ${{ always() }}` so it runs even when the runner job fails.

```yaml
jobs:
  start-brev-runner:
    runs-on: ubuntu-latest
    outputs:
      mapping: ${{ steps.brev-start.outputs.mapping }}
      instances: ${{ steps.brev-start.outputs.instances }}
    steps:
      - name: Create Brev runner
        id: brev-start
        uses: omsf/start-brev-gha-runner@v1
        with:
          brev_instance_type: g5.xlarge,g6.xlarge
          brev_org: my-team
        env:
          BREV_TOKEN: ${{ secrets.BREV_TOKEN }}
          GH_PAT: ${{ secrets.GH_PAT }}

  test:
    needs: start-brev-runner
    runs-on: ${{ fromJSON(needs.start-brev-runner.outputs.instances) }}
    steps:
      - uses: actions/checkout@v4
      - run: nvidia-smi

  stop-brev-runner:
    runs-on: ubuntu-latest
    needs: [start-brev-runner, test]
    if: ${{ always() }}
    steps:
      - name: Remove Brev runner
        uses: omsf/stop-brev-gha-runner@v1
        with:
          instance_mapping: ${{ needs.start-brev-runner.outputs.mapping }}
          brev_org: my-team
        env:
          BREV_TOKEN: ${{ secrets.BREV_TOKEN }}
          GH_PAT: ${{ secrets.GH_PAT }}
```

`brev delete` permanently removes each instance and its storage. This action
does not use `brev stop`, which would retain billable storage.
