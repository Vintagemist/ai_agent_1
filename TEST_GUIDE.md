# Auto-Fix Agent Testing Guide

## Prerequisites

1. **Set up your Anthropic API key**:
   ```bash
   export ANTHROPIC_API_KEY="your-api-key-here"
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Test Scenarios

### 1. Local Script Testing (Unit Test)

Test the Python script directly with mock review comments:

#### Test 1a: Dry-run mode (safe, no file changes)
```bash
python3 scripts/fix_review_agent.py \
  --comments test_review_comments.json \
  --repo-root . \
  --dry-run \
  --model claude-haiku-4-5-20251001 \
  --min-confidence low
```

**Expected output**: Shows what fixes would be applied without actually modifying files.

#### Test 1b: Apply fixes (modifies test_file.py)
```bash
python3 scripts/fix_review_agent.py \
  --comments test_review_comments.json \
  --repo-root . \
  --model claude-haiku-4-5-20251001 \
  --min-confidence medium
```

**Expected output**:
- Applies type hints to the function
- May optimize the loop based on the review comment
- Shows "Applied" messages for successful fixes

#### Test 1c: Batch mode (processes multiple comments per file in one call)
```bash
python3 scripts/fix_review_agent.py \
  --comments test_review_comments.json \
  --repo-root . \
  --batch \
  --dry-run \
  --model claude-haiku-4-5-20251001 \
  --min-confidence medium
```

**Expected output**: Groups comments by file and processes them together.

### 2. GitHub Actions Workflow Testing

#### Test 2a: Manual workflow dispatch (safest for testing)

1. Push your changes to a test branch:
   ```bash
   git add .
   git commit -m "Test auto-fix agent"
   git push origin test_agent
   ```

2. Create a test PR:
   ```bash
   gh pr create --title "Test Auto-Fix Agent" --body "Testing the auto-fix functionality"
   ```

3. Add some review comments to the PR:
   - Go to the PR on GitHub
   - Click on "Files changed"
   - Add line comments like:
     - "Add type hints here"
     - "Use list comprehension instead"
     - "Add error handling"

4. Run the workflow manually:
   - Go to Actions → "Fix code review comments"
   - Click "Run workflow"
   - Enter your branch name: `test_agent`
   - Click "Run workflow"

**Expected behavior**:
- Workflow fetches review comments
- Processes them with Claude AI
- Applies fixes and commits to the branch
- Posts a comment on the PR when done

#### Test 2b: Automatic trigger with keywords

1. Add a review comment with the magic keyword:
   ```
   @auto-fix Please add type hints to this function
   ```

2. The workflow should trigger automatically and apply the fix.

#### Test 2c: Test with PR label

1. Add the label `auto-fix-enabled` to your PR
2. Add any review comment (without keywords)
3. The workflow should process all comments automatically

### 3. Configuration Testing

#### Test 3a: Disable the agent
Edit `.github/auto-fix.yml`:
```yaml
enabled: false
```

Add a review comment → workflow should skip processing.

#### Test 3b: Test file filters
Edit `.github/auto-fix.yml` to only process Python files:
```yaml
include:
  - "**/*.py"
```

Add comments to a `.js` file → should be skipped.

#### Test 3c: Test confidence threshold
Edit `.github/auto-fix.yml`:
```yaml
ai:
  confidence_threshold: "high"  # Only apply high-confidence fixes
```

Add ambiguous review comments → should skip low/medium confidence fixes.

### 4. Security Testing

#### Test 4a: Fork protection
1. Create a fork of the repository
2. Create a PR from the fork
3. Add review comments
4. **Expected**: Workflow should skip (security check fails)

#### Test 4b: Permission check
1. Have someone without write access add a review comment
2. **Expected**: Workflow should skip (permission check fails)

### 5. Edge Cases

#### Test 5a: Invalid file path
```json
[
  {
    "path": "nonexistent.py",
    "line": 5,
    "body": "Fix this"
  }
]
```
**Expected**: Script should skip with "file not found" message.

#### Test 5b: Empty comments array
```bash
echo "[]" > empty_comments.json
python3 scripts/fix_review_agent.py --comments empty_comments.json --repo-root . --dry-run
```
**Expected**: "No comments to process"

#### Test 5c: Large file (exceeds max_file_size_bytes)
Create a large file and test → should be skipped by size limit.

#### Test 5d: Many comments (exceeds max_comments_per_pr)
Add 25+ review comments to a PR → should only process first 20 (based on config).

### 6. Validation Checklist

After running tests, verify:

- [ ] Dry-run mode doesn't modify files
- [ ] Actual run applies fixes correctly
- [ ] Git commits are created with proper message
- [ ] PR gets a comment notification
- [ ] Security checks block unauthorized runs
- [ ] Configuration settings are respected
- [ ] File filters work correctly
- [ ] Confidence threshold filtering works
- [ ] Error handling doesn't crash the workflow
- [ ] Batch mode groups comments efficiently

## Troubleshooting

### Issue: "Set ANTHROPIC_API_KEY environment variable"
**Solution**: Add `ANTHROPIC_API_KEY` to your repository secrets:
1. Go to Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Name: `ANTHROPIC_API_KEY`
4. Value: Your Anthropic API key

### Issue: "Permission denied" when pushing
**Solution**: Make sure the workflow has `contents: write` permission (already configured).

### Issue: "No review comments to process"
**Solution**: Make sure you're testing on a PR with actual line-level review comments.

### Issue: Fixes not being applied
**Solution**: Check:
1. Confidence threshold (lower it to `low` for testing)
2. File filters (make sure file type is included)
3. Agent is enabled in config
4. Review comment format is correct

## Monitoring

Check workflow logs:
```bash
gh run list --workflow=fix-review-comments.yml
gh run view <run-id> --log
```

Check applied changes:
```bash
git log -1 --stat
git diff HEAD~1
```

## Clean Up

After testing:
```bash
# Remove test files
rm test_review_comments.json test_file.py empty_comments.json

# Close test PR
gh pr close <pr-number>

# Delete test branch
git push origin --delete test_agent
```
