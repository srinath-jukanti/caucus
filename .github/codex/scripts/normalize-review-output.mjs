import { readFileSync, writeFileSync } from 'node:fs'

const input = process.argv[2] || 'codex-review.raw.md'
const output = process.argv[3] || 'codex-review.json'
const configPath = process.argv[4] || '.github/codex/review-config.json'

const severityRank = {
  nit: 0,
  low: 1,
  medium: 2,
  high: 3,
  blocker: 4,
}

function extractJson(text) {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i)
  if (fenced) {
    return JSON.parse(fenced[1])
  }

  const start = text.indexOf('{')
  if (start === -1)
    throw new Error('Codex review output did not contain a JSON object.')

  let depth = 0
  let inString = false
  let escaped = false

  for (let index = start; index < text.length; index += 1) {
    const char = text[index]

    if (inString) {
      if (escaped) {
        escaped = false
      } else if (char === '\\') {
        escaped = true
      } else if (char === '"') {
        inString = false
      }
      continue
    }

    if (char === '"') inString = true
    if (char === '{') depth += 1
    if (char === '}') depth -= 1

    if (depth === 0) {
      return JSON.parse(text.slice(start, index + 1))
    }
  }

  throw new Error('Codex review output had an unterminated JSON object.')
}

function matchesPattern(filePath, pattern) {
  if (pattern.startsWith('**/*.')) {
    return filePath.endsWith(pattern.slice(4))
  }

  if (pattern.startsWith('*.')) {
    return filePath.endsWith(pattern.slice(1))
  }

  return filePath === pattern
}

const raw = readFileSync(input, 'utf8')
const config = JSON.parse(readFileSync(configPath, 'utf8'))
const parsed = extractJson(raw)
const minimumRank = severityRank[config.minimumSeverity] ?? severityRank.medium
const enabledCategories = new Set(config.enabledCategories || [])
const ignoredPaths = config.ignoredPaths || []

const findings = Array.isArray(parsed.findings) ? parsed.findings : []
const normalizedFindings = findings
  .map((finding) => ({
    severity: String(finding.severity || 'medium').toLowerCase(),
    category: String(finding.category || 'maintainability').toLowerCase(),
    path: String(finding.path || ''),
    line: Number(finding.line),
    title: String(finding.title || 'Review finding').trim(),
    body: String(finding.body || '').trim(),
    confidence: Number.isFinite(Number(finding.confidence))
      ? Number(finding.confidence)
      : 0.5,
    suggested_fix: finding.suggested_fix
      ? String(finding.suggested_fix).trim()
      : '',
    should_block_merge: Boolean(finding.should_block_merge),
  }))
  .filter((finding) => severityRank[finding.severity] !== undefined)
  .filter((finding) => severityRank[finding.severity] >= minimumRank)
  .filter(
    (finding) =>
      !enabledCategories.size || enabledCategories.has(finding.category),
  )
  .filter(
    (finding) =>
      finding.path &&
      !ignoredPaths.some((pattern) => matchesPattern(finding.path, pattern)),
  )
  .filter((finding) => finding.body)

const hasBlocking = normalizedFindings.some(
  (finding) =>
    (config.blockingSeverities || []).includes(finding.severity) ||
    finding.should_block_merge,
)

const report = {
  summary: String(parsed.summary || '').trim() || 'Codex completed the review.',
  decision: hasBlocking
    ? 'request_changes'
    : normalizedFindings.length
      ? 'comment'
      : 'approve',
  findings: normalizedFindings,
}

writeFileSync(output, `${JSON.stringify(report, null, 2)}\n`)
