# Codegen Orchestration via GitHub Actions

This document describes how to delegate tasks to Codegen AI agents via GitHub Actions comments in pull requests.

## Overview

The `.github/workflows/codegen-orchestrator.yml` workflow allows you to dispatch Codegen cloud agents by mentioning `@codegen-sh` in PR comments. The agent will work on the PR branch, make changes, run tests, and push commits directly to the PR.

## Setup

### 1. Required Secrets

Add the following secrets to your GitHub repository (Settings → Secrets and variables → Actions):

- **`CODEGEN_API_KEY`** — Your Codegen API key from [codegen.com](https://codegen.com)
- **`CODEGEN_ORG_ID`** — Your Codegen organization ID (numeric)

### 2. Repository Setup in Codegen

1. Log in to [codegen.com](https://codegen.com)
2. Go to your organization settings
3. Connect your GitHub repository
4. Verify the repository appears in the list with `setup_status: "ready"`

## Usage

### Basic Syntax

In any pull request comment, mention `@codegen-sh` followed by a task description:

```
@codegen-sh Fix the failing tests in test_tracks.py
```

The workflow will:
1. ✅ Add a 🚀 reaction to your comment
2. 🤖 Post an acknowledgement comment with task details
3. 🔧 Create a Codegen agent run with the task
4. 📋 Post the run ID and tracking link

### Examples

**Fix failing tests:**
```
@codegen-sh Fix the failing type check errors in app/mcp/server.py
```

**Implement a feature:**
```
@codegen-sh Add error handling for invalid BPM values in the transition scoring function
```

**Refactor code:**
```
@codegen-sh Refactor the _build_transition_matrix function to use numpy vectorization
```

**Default task (no description):**
```
@codegen-sh
```
This will use the default task: "Review and implement requested changes"

## How It Works

### Workflow Trigger

The workflow is triggered by:
- Event: `issue_comment.created`
- Condition: Comment is on a pull request AND contains `@codegen-sh`

### Workflow Steps

1. **Extract task from comment**
   - Parses the comment body to extract the task description after `@codegen-sh`
   - Falls back to default task if no description provided
   - Captures PR metadata (number, title, URL)

2. **Add reaction**
   - Adds 🚀 reaction to the triggering comment for immediate feedback

3. **Post acknowledgement**
   - Posts a comment confirming the agent dispatch
   - Shows task description, agent type, and requester

4. **Create Codegen agent run**
   - Builds a prompt with PR context and task description
   - Calls Codegen API to create an agent run
   - Metadata includes PR number, workflow name, and requester

5. **Post run details or error**
   - On success: Posts run ID and tracking link
   - On failure: Posts error message with troubleshooting hints

### Agent Constraints

The Codegen agent is instructed to:
- ✅ Work on the PR branch (checkout existing branch)
- ✅ Run tests after each change
- ✅ Use conventional commit messages
- ✅ Push changes to the PR branch (NOT create a new PR)
- ✅ Fix failing tests before pushing

### Agent Context

The prompt sent to Codegen includes:
- PR number and title
- PR URL
- Task description
- Execution constraints

Example prompt:
```
## Context
PR #42: BPM-123: Fix transition scoring

https://github.com/evgenygurin/dj-techno-set-builder/pull/42

## Your Task
Fix the failing tests in test_tracks.py

## Constraints
- Work on the PR branch (checkout the branch from the PR)
- Run tests after each change
- Commit with conventional commit messages
- Push changes to the PR branch (do NOT create a new PR)
- If tests fail, fix them before pushing
```

## Monitoring Progress

### On Codegen Dashboard

1. Click the tracking link in the GitHub comment
2. View real-time agent logs and status
3. See tool calls, thoughts, and outputs

### On GitHub PR

- Agent commits will appear in the PR timeline
- CI checks will run on agent's commits
- Review agent changes like any other PR commits

## Troubleshooting

### Workflow not triggering

**Symptom:** No reaction or comment after mentioning `@codegen-sh`

**Causes:**
- Comment is not on a pull request (workflow only runs on PRs)
- `@codegen-sh` mention is missing or misspelled
- Workflow file has syntax errors

**Solution:**
1. Verify you're commenting on a PR (not an issue)
2. Check spelling: `@codegen-sh` (case-sensitive)
3. Review workflow logs in Actions tab

### Agent run creation fails

**Symptom:** "Failed to create Codegen agent run" comment

**Causes:**
- Invalid or missing `CODEGEN_API_KEY` secret
- Invalid or missing `CODEGEN_ORG_ID` secret
- Repository not set up in Codegen
- API rate limits or billing limits

**Solution:**
1. Verify secrets are set correctly in repository settings
2. Verify repository is connected in Codegen dashboard
3. Check Codegen account status and limits
4. Review workflow logs for detailed error message

### Agent doesn't push changes

**Symptom:** Agent run completes but no commits appear on PR

**Causes:**
- Agent encountered errors and couldn't complete the task
- Tests failed and agent stopped
- Agent created commits but failed to push

**Solution:**
1. Review agent logs on Codegen dashboard
2. Check if agent encountered blockers or errors
3. Consider resuming the agent run with clarifications
4. If needed, manually pull agent's branch and push

## Advanced Usage

### Custom metadata

The workflow adds metadata to each agent run:
```json
{
  "pr_number": 42,
  "gh_workflow": "codegen-orchestrator",
  "triggered_by": "evgenygurin"
}
```

This metadata is visible in Codegen dashboard and can be used for filtering/reporting.

### Integration with codegen-bridge plugin

If you have the `codegen-bridge` Claude Code plugin installed, you can:

1. **Monitor agent status from CLI:**
   ```
   /cg-status
   ```

2. **View agent logs from CLI:**
   ```
   /cg-logs <run_id>
   ```

3. **Resume blocked agent:**
   ```python
   codegen_resume_run(
       run_id=<run_id>,
       prompt="Fix the import error by adding the missing dependency"
   )
   ```

## Security Considerations

- **API keys:** Never commit `CODEGEN_API_KEY` to the repository. Always use GitHub Secrets.
- **Permissions:** The workflow has `pull-requests: write` permission to post comments and reactions.
- **Untrusted input:** Task descriptions are user-provided. Codegen API sanitizes inputs, but avoid sensitive data in task descriptions.
- **Branch protection:** If the PR branch is protected, ensure Codegen has push permissions (via GitHub App or PAT).

## Workflow Permissions

```yaml
permissions:
  contents: read          # Read repository contents
  issues: write           # Post comments on PRs
  pull-requests: write    # Add reactions and metadata
```

## API Endpoints

The workflow uses Codegen API v1:
- **Base URL:** `https://api.codegen.com/v1`
- **Create run:** `POST /organizations/{org_id}/agent/run`
- **Authentication:** Bearer token in `Authorization` header

## Related Documentation

- [Codegen API Reference](https://docs.codegen.com/api-reference/overview)
- [Codegen Agent Runs](https://docs.codegen.com/api-reference/agents/create-agent-run)
- [GitHub Actions: issue_comment event](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#issue_comment)
- [codegen-bridge Plugin](../docs/plans/2026-02-21-codegen-bridge-design.md)

## Changelog

- **2026-03-05:** Initial implementation of `@codegen-sh` orchestration workflow
