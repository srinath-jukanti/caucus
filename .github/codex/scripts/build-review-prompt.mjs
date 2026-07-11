import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'

const baseRef = process.env.BASE_REF
const headRef = process.env.HEAD_REF
const prNumber = process.env.PR_NUMBER
const reviewWorktree = process.env.REVIEW_WORKTREE || '.'
const qualityOutputPath = process.env.QUALITY_OUTPUT || ''
const output = process.argv[2] || 'codex-review-prompt.md'

if (!baseRef || !headRef || !prNumber) {
  throw new Error('BASE_REF, HEAD_REF, and PR_NUMBER are required.')
}

function git(args, options = {}) {
  return execFileSync('git', ['-C', reviewWorktree, ...args], {
    encoding: 'utf8',
    maxBuffer: 20 * 1024 * 1024,
    ...options,
  }).trimEnd()
}

function readIfExists(filePath) {
  return existsSync(filePath) ? readFileSync(filePath, 'utf8') : ''
}

function readTargetIfExists(filePath) {
  const targetPath = path.join(reviewWorktree, filePath)
  return existsSync(targetPath) ? readFileSync(targetPath, 'utf8') : ''
}

function truncate(value, maxChars) {
  if (value.length <= maxChars) return value
  return `${value.slice(0, maxChars)}\n...[truncated ${value.length - maxChars} chars]`
}

function parseChangedLines(diff) {
  const result = new Map()
  let currentFile = null
  let newLine = 0

  for (const line of diff.split('\n')) {
    if (line.startsWith('+++ b/')) {
      currentFile = line.slice('+++ b/'.length)
      if (!result.has(currentFile)) result.set(currentFile, new Set())
      continue
    }

    if (!currentFile) continue

    const hunk = line.match(/^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@/)
    if (hunk) {
      newLine = Number(hunk[1])
      continue
    }

    if (line.startsWith('+') && !line.startsWith('+++')) {
      result.get(currentFile).add(newLine)
      newLine += 1
    } else if (line.startsWith('-') && !line.startsWith('---')) {
      continue
    } else if (!line.startsWith('\\')) {
      newLine += 1
    }
  }

  return [...result.entries()]
    .map(
      ([file, lines]) =>
        `${file}: ${[...lines].sort((a, b) => a - b).join(', ') || '(no added lines)'}`,
    )
    .join('\n')
}

const base = `origin/${baseRef}`
const prompt = readIfExists('.github/codex/prompts/review.md')
const config = readIfExists('.github/codex/review-config.json')
const rules = readIfExists('.github/codex/review-rules.md')
const diffStat = git(['diff', '--stat', `${base}...HEAD`])
const diffNameOnly = git(['diff', '--name-only', `${base}...HEAD`])
const diff = git(['diff', `${base}...HEAD`])
const commitLog = git(['log', '--reverse', '--format=%h %s', `${base}..HEAD`])
const commitDetails = git([
  'log',
  '--reverse',
  '--stat',
  '--format=commit %H%nAuthor: %an <%ae>%nSubject: %s%nBody:%n%b',
  `${base}..HEAD`,
])
const repoFiles = git(['ls-files'])

// Commit history newest-first with +/-line stats for multi-commit false-positive reduction.
const commitHistoryNewestFirst = git([
  'log',
  '--format=## %h %s',
  '--stat',
  `${base}..HEAD`,
])

// Output of the real quality gates (ruff format/lint + pytest) run against the PR's
// merged code — gives the model ground truth instead of guesses.
const qualityOutput = qualityOutputPath
  ? readIfExists(qualityOutputPath) || '(quality output file was empty)'
  : '(quality checks were not run)'

const contextFiles = [
  'README.md',
  'AGENT_SETUP.md',
  'pyproject.toml',
  '.github/workflows/ci.yml',
  '.github/workflows/codex-review.yml',
  '.github/codex/review-config.json',
  '.github/codex/review-rules.md',
].filter((file) => existsSync(path.join(reviewWorktree, file)))

const changedFiles = diffNameOnly.split('\n').filter(Boolean)
const changedFileContext = changedFiles
  .filter((file) => existsSync(path.join(reviewWorktree, file)))
  .slice(0, 30)
  .map((file) => {
    const body = truncate(readTargetIfExists(file), 12000)
    return `### ${file}\n\n\`\`\`\n${body}\n\`\`\``
  })
  .join('\n\n')

const staticContext = contextFiles
  .map((file) => {
    const body = truncate(readTargetIfExists(file), 8000)
    return `### ${file}\n\n\`\`\`\n${body}\n\`\`\``
  })
  .join('\n\n')

const finalPrompt = `# Review Instructions

${prompt}

# Review Configuration

\`\`\`json
${config}
\`\`\`

# Repository Review Rules

${rules}

# Pull Request Metadata

- Base branch: ${baseRef}
- Head branch: ${headRef}
- PR number: ${prNumber}
- Working directory: ${path.resolve('.')}
- Review worktree: ${path.resolve(reviewWorktree)}

# Commit History (newest first)

Use this to understand the PR's evolution. If an early commit introduced an issue that a later commit already fixed, do NOT flag it as an open finding.

\`\`\`
${truncate(commitHistoryNewestFirst, 12000)}
\`\`\`

# Pull Request Commit History

\`\`\`
${truncate(commitLog, 12000)}
\`\`\`

# Pull Request Commit Details

\`\`\`
${truncate(commitDetails, 40000)}
\`\`\`

# Quality Gate Output

This is the output of \`ruff format --check\`, \`ruff check\`, and \`pytest\` run against the PR's merged code. Use this as ground truth for formatting, lint, and test failures — do not speculate about issues that are absent from this output.

\`\`\`
${truncate(qualityOutput, 16000)}
\`\`\`

# Repository File List

\`\`\`
${truncate(repoFiles, 12000)}
\`\`\`

# Changed RIGHT-side Lines Eligible for Inline Comments

\`\`\`
${parseChangedLines(diff)}
\`\`\`

# Important Repository Context

${staticContext || '(none)'}

# Changed File Context

${changedFileContext || '(none)'}

# Diff Stat

\`\`\`
${diffStat}
\`\`\`

# Full Diff

\`\`\`diff
${truncate(diff, 120000)}
\`\`\`
`

writeFileSync(output, finalPrompt)
