# Quick Start: Testing the Auto-Fix Agent

## Overview

Your auto-fix agent is ready! Here's how to test it end-to-end.

## Setup (One-time)

### 1. Add API Key to GitHub Secrets

1. Go to your repository on GitHub
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Name: `ANTHROPIC_API_KEY`
5. Value: Your Anthropic API key
6. Click **Add secret**

### 2. Verify Workflow is Enabled

The workflow file is at `.github/workflows/fix-review-comments.yml`

Check that it's committed and pushed to your repository.

## Quick Test (5 minutes)

### Option A: Manual Workflow Test (Recommended for first test)

1. **Create a test file with obvious issues:**

```bash
cat > example.py << 'EOF'
def calculate_total(items, tax):
    sum = 0
    for item in items:
        sum = sum + item
    return sum * tax
EOF

git add example.py
git commit -m "Add test file for auto-fix"
git push origin test_agent
```

2. **Create a Pull Request:**

```bash
gh pr create --title "Test Auto-Fix Agent" --body "Testing automatic code review fixes" --base main --head test_agent
```

3. **Add some review comments:**
   - Go to the PR on GitHub → Files changed
   - Click the "+" next to line 1
   - Add comment: "Add type hints to function parameters"
   - Click the "+" next to line 2
   - Add comment: "Don't use 'sum' as variable name, it shadows built-in"
   - Submit the review

4. **Run the workflow manually:**
   - Go to **Actions** → **Fix code review comments**
   - Click **Run workflow**
   - Branch: `test_agent` (or your branch name)
   - Click **Run workflow** button

5. **Watch the magic happen:**
   - The workflow will run (takes ~30-60 seconds)
   - Check the Actions tab for logs
   - The agent will commit fixes to your branch
   - You'll see a comment on the PR: "🤖 Code review fixes applied"

6. **Verify the changes:**

```bash
git pull origin test_agent
cat example.py
```

### Option B: Automatic Trigger Test

1. Create a PR (same as above)
2. Add a review comment with the magic keyword:
   ```
   @auto-fix Add type hints to this function
   ```
3. The workflow triggers automatically!

### Option C: Auto-apply with Label

1. Create a PR
2. Add the label `auto-fix-enabled` to the PR
3. Add any review comments (no keywords needed)
4. The agent processes all comments automatically

## What to Look For

### ✅ Success Indicators

- Workflow completes without errors
- New commit appears on your branch with message: "Apply fixes from code review"
- Files are modified correctly
- PR gets a comment from github-actions bot

### ❌ Common Issues

**"Set ANTHROPIC_API_KEY as a repository secret"**
- Solution: Add the secret as described in Setup step 1

**"No review comments to process"**
- Make sure you added line-level review comments (not general PR comments)

**"Security checks failed"**
- PR must be from the same repository (not a fork)
- Comment author must have write access

**Fixes not applied**
- Check confidence threshold in `.github/auto-fix.yml`
- Lower it to `low` for testing

## Configuration

Edit `.github/auto-fix.yml` to customize behavior:

```yaml
# Disable the agent temporarily
enabled: false

# Change confidence threshold (low/medium/high)
ai:
  confidence_threshold: "low"  # More aggressive fixes

# Change trigger keywords
triggers:
  keywords:
    - "@fix-it"
    - "/auto-fix"
```

## Testing Different Scenarios

### Test 1: Type Hints

```python
def add(a, b):
    return a + b
```

Review comment: "Add type hints"

Expected fix:
```python
def add(a: int, b: int) -> int:
    return a + b
```

### Test 2: Code Style

```python
x=1+2
```

Review comment: "Add spaces around operators per PEP 8"

Expected fix:
```python
x = 1 + 2
```

### Test 3: Documentation

```python
def complex_function(data):
    # ... some logic
    return result
```

Review comment: "Add a docstring explaining what this function does"

Expected fix includes docstring.

## Batch Mode Testing

To process multiple comments per file more efficiently:

```bash
python3 scripts/fix_review_agent.py \
  --comments review-comments.json \
  --repo-root . \
  --batch \
  --model claude-haiku-4-5-20251001
```

## Monitoring

### View workflow logs:

```bash
gh run list --workflow=fix-review-comments.yml
gh run view <run-id> --log
```

### Check what changed:

```bash
git log -1 --stat
git diff HEAD~1
```

### View PR comments:

```bash
gh pr view <pr-number>
```

## Cleanup After Testing

```bash
# Close test PR
gh pr close <pr-number>

# Delete test branch
git checkout main
git branch -D test_agent
git push origin --delete test_agent

# Remove test files
rm example.py test_review_comments.json test_file.py
```

## Next Steps

Once testing is successful:

1. **Enable on real PRs**: Set `auto_apply: true` in config (careful!)
2. **Customize file filters**: Edit `include` section to match your project
3. **Adjust confidence**: Use `high` for production to be conservative
4. **Train your team**: Share the `@auto-fix` keyword

## Troubleshooting

See `TEST_GUIDE.md` for comprehensive troubleshooting and advanced testing scenarios.

## Support

- File issues: https://github.com/anthropics/claude-code/issues
- Check logs in Actions tab
- Review agent output in workflow logs
