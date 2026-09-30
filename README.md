# stop-brev-gha-runner

Remove ephemeral, repository-scoped GitHub Actions runners from
[NVIDIA Brev](https://docs.nvidia.com/brev/llms.txt). The action removes each
GitHub runner registration before permanently deleting its Brev instance with
`brev delete` through the [`gha-runner`](https://gha-runner.readthedocs.io/)
teardown lifecycle.

## Setup

1. In the Brev organization that owns the runners, create a
   [Brev API key](https://docs.nvidia.com/brev/guides/api-keys) with
   **Read & Write** access. Copy the full key when it is shown: Brev shows it
   only once, and it expires on the date you configure.
2. Add the key as the repository secret `BREV_API_KEY`.
3. Add a GitHub token able to manage repository self-hosted runners as
   `GH_PAT`.

## Inputs

| Input | Required | Default | Description |
| --- | --- | --- | --- |
| `instance_mapping` | yes | | The start action's `mapping` output: a JSON object mapping Brev instance names to runner labels. |
| `repo` | no | current repository | Repository containing the runner registrations. |

The action requires non-empty `BREV_API_KEY` and `GH_PAT` environment variables.
The API key selects its organization automatically.

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
        uses: omsf-eco-infra/start-brev-gha-runner@main
        with:
          brev_instance_type: g5.xlarge,g6.xlarge
        env:
          BREV_API_KEY: ${{ secrets.BREV_API_KEY }}
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
        uses: omsf-eco-infra/stop-brev-gha-runner@main
        with:
          instance_mapping: ${{ needs.start-brev-runner.outputs.mapping }}
        env:
          BREV_API_KEY: ${{ secrets.BREV_API_KEY }}
          GH_PAT: ${{ secrets.GH_PAT }}
```

`brev delete` permanently removes each instance and its storage. This action
does not use `brev stop`, which would retain billable storage.

The supplied `instance_mapping` is used for deletion even when a GitHub runner
registration is already missing. Pin each action to a commit SHA in production
workflows.
