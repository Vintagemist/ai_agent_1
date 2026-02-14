# ai_agent_1

<!-- Dummy change for PR testing -->

## Creating an Agent That Fixes Code Review Comments IN GITHUB ACTIONS PIPELINE

This section describes how to create an agent that automatically addresses code review feedback from reviewers.

### Overview

The agent takes **reviewer comments** (from a code review tool or pull request) and applies fixes directly in the codebase so that the same comments can be resolved without manual edits.

### Prerequisites

- Access to the codebase under review
- Code review comments in a structured form (e.g., file path, line/range, comment text)
- Ability to run the agent in your environment (e.g., Cursor, CLI, or CI)

### Steps to Create the Agent

1. **Ingest review comments**
   - Parse comments from your review source (GitHub/GitLab/Bitbucket API, exported JSON, or inline in the PR description).
   - For each comment, capture: **file path**, **line or range**, **comment text**, and optionally **suggested change** or **severity**.

2. **Map comments to code**
   - Resolve each comment to the exact file and line(s) in the repo.
   - Handle moved/renamed files if the review is from an older revision.

3. **Generate fixes**
   - For each comment, use the agent (e.g., an LLM or rule-based engine) to:
     - Understand the reviewer’s request (bug fix, style, security, performance, etc.).
     - Propose a concrete code change (patch or edit).
     - Optionally explain the fix in a short reply for the review thread.

4. **Apply changes**
   - Apply the proposed edits to the working tree (e.g., via search-and-replace, AST-based edits, or patch application).
   - Run linters and tests to ensure no regressions.

5. **Report back**
   - Update the review thread with “Fixed” or attach the applied patch.
   - Optionally post a summary of what was changed and which comments were addressed.

### GitHub PR Pipeline Integration

The agent is integrated into the GitHub PR pipeline so it can run **automatically** when review comments are added or **manually** on demand.

#### Triggers

| Trigger | When it runs |
|--------|----------------|
| **Automatic** | When a reviewer posts a **line-level comment** on a PR (`pull_request_review_comment`) or when a **review is submitted** (`pull_request_review`). |
| **Manual** | From the **Actions** tab: choose the workflow **"Fix code review comments"** → **Run workflow**, select branch, then **Run workflow**. |

#### How to use

1. **Automatic**
   - Create or open a PR. Once a reviewer adds comments (on the code or as a review), the workflow runs on that PR.
   - The workflow uses the repo’s `GITHUB_TOKEN` (or a PAT with `repo` scope) to read comments and push fixes.

2. **Manual**
   - Go to **Actions** → **Fix code review comments** → **Run workflow**.
   - Pick the branch (usually the PR branch you want to fix).
   - Click **Run workflow**. The agent will fetch open review comments for that branch’s PR and apply fixes.

#### Setup

- Workflow file: [`.github/workflows/fix-review-comments.yml`](.github/workflows/fix-review-comments.yml).
- Agent script: [**`scripts/fix_review_agent.py`**](scripts/fix_review_agent.py) — reads GitHub PR review comments (JSON), calls an LLM to generate fixes, and applies edits to the repo.
- **Secrets** (in repo **Settings → Secrets and variables → Actions**):
  - **`OPENAI_API_KEY`** or **`OPENROUTER_API_KEY`** (one required for the agent): API key so the agent can generate fixes. Use **OpenRouter** (e.g. from [openrouter.ai](https://openrouter.ai)) by setting `OPENROUTER_API_KEY`; the agent then uses `https://openrouter.ai/api/v1` and supports any OpenRouter model (e.g. `--model openai/gpt-4o-mini`). Without either key, the workflow runs but skips applying fixes.
  - **`GH_TOKEN`** (optional): Use if you need a PAT instead of the default `GITHUB_TOKEN` (e.g. for private forks or cross-repo).
- Ensure the default `GITHUB_TOKEN` has **Contents: read/write** and **Pull requests: read/write** (default in GitHub Actions).

#### What the workflow does

1. Triggers on review comments or review submission (and on manual run).
2. Checks out the PR branch.
3. Fetches review comments via the GitHub API (`gh api .../pulls/{pr}/comments`) and writes them to a JSON file.
4. Runs the **fix agent** ([`scripts/fix_review_agent.py`](scripts/fix_review_agent.py)): loads comments, for each comment uses the OpenAI API to generate a code fix, then applies the edit to the file.
5. If any files changed, commits and pushes to the branch and sets `changes=yes`.
6. Posts a short comment on the PR when fixes were pushed.

### Running the agent locally

From the repo root, with review comments in GitHub API JSON format:

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=your_key_here
# Or use OpenRouter: export OPENROUTER_API_KEY=your_openrouter_key
# Optional: export comments from a PR, e.g. gh api "repos/OWNER/REPO/pulls/PR/comments" > comments.json
python scripts/fix_review_agent.py --comments comments.json [--repo-root .] [--dry-run] [--model gpt-4o-mini]
```

- **`--dry-run`**: Print proposed fixes without editing files.
- **`--model`**: Model ID (default: `gpt-4o-mini`). For OpenRouter use e.g. `openai/gpt-4o-mini` or another [OpenRouter model](https://openrouter.ai/docs/models).
- **OpenRouter**: If `OPENROUTER_API_KEY` is set, the agent uses OpenRouter’s API; no need to set `OPENAI_API_KEY`.

The JSON file must be an array of GitHub [pull request review comment](https://docs.github.com/en/rest/pulls/comments) objects (e.g. from `GET /repos/{owner}/{repo}/pulls/{pull_number}/comments`).

### Testing the agent

**Option A — Local (quick)**

1. From the repo root:
   ```bash
   pip install -r requirements.txt
   export OPENROUTER_API_KEY=your_key   # or OPENAI_API_KEY
   ```
2. Dry-run (no file changes):
   ```bash
   python scripts/fix_review_agent.py --comments scripts/sample-review-comments.json --dry-run
   ```
   You should see the agent suggest a fix for `README.md` line 1.
3. Apply for real:
   ```bash
   python scripts/fix_review_agent.py --comments scripts/sample-review-comments.json
   ```
   Then check `README.md` and revert if you like (`git checkout -- README.md`).

**Option B — GitHub Actions (full pipeline)**

1. Add **`OPENROUTER_API_KEY`** (or **`OPENAI_API_KEY`**) in the repo under **Settings → Secrets and variables → Actions**.
2. Push this repo to GitHub, create a new branch, and open a **Pull Request**.
3. On the PR, add a **line-level review comment** (e.g. on a line in `README.md` or any file).
4. Either:
   - Wait for the workflow to run automatically after the comment, or  
   - Go to **Actions → “Fix code review comments” → Run workflow**, choose your PR branch, then **Run workflow**.
5. Check the workflow run log and the PR: the agent should push a commit with fixes and post a comment.

### Other integration options

- **IDE/Editor**: Use an in-editor agent that reads comments from the review panel and suggests or applies edits in the current file.

### Best Practices

- **Idempotency**: Re-running the agent on the same comments after fixes are applied should not double-apply or conflict.
- **Traceability**: Log which comment led to which edit so reviewers can verify.
- **Safety**: Prefer suggesting patches for human approval in critical repos, or restrict to non-production branches.
- **Testing**: After applying fixes, run the project’s test suite and fix any failures before marking comments as resolved.
