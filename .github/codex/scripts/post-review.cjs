const fs = require('node:fs')

const severityLabel = {
  blocker: 'Blocker',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
  nit: 'Nit',
}

function parseChangedLines(patch) {
  const lines = new Set()
  let newLine = 0

  for (const line of (patch || '').split('\n')) {
    const hunk = line.match(/^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@/)
    if (hunk) {
      newLine = Number(hunk[1])
      continue
    }

    if (line.startsWith('+') && !line.startsWith('+++')) {
      lines.add(newLine)
      newLine += 1
    } else if (line.startsWith('-') && !line.startsWith('---')) {
      continue
    } else if (!line.startsWith('\\')) {
      newLine += 1
    }
  }

  return lines
}

function formatFinding(finding) {
  const pieces = [
    `**${severityLabel[finding.severity] || finding.severity} / ${finding.category}: ${finding.title}**`,
    '',
    finding.body,
  ]

  if (finding.suggested_fix) {
    pieces.push('', `Suggested fix: ${finding.suggested_fix}`)
  }

  pieces.push('', `Confidence: ${Math.round(finding.confidence * 100)}%`)

  return pieces.join('\n')
}

function normalizeDecision(report, shouldRequestChanges) {
  if (shouldRequestChanges) return 'request_changes'
  if (report.decision === 'approve' && !report.findings?.length)
    return 'approve'
  if (report.decision === 'request_changes') return 'request_changes'
  return report.findings?.length ? 'comment' : 'approve'
}

function decisionLabel(decision) {
  if (decision === 'request_changes') return '🛑 Request changes'
  if (decision === 'approve') return '✅ Approved'
  return '💬 Comment'
}

module.exports = async ({ github, context, core }) => {
  const report = JSON.parse(fs.readFileSync('codex-review.json', 'utf8'))
  const config = JSON.parse(
    fs.readFileSync('.github/codex/review-config.json', 'utf8'),
  )
  const marker =
    config.summaryCommentMarker || '<!-- siteally-codex-review-summary -->'
  const pull = context.payload.pull_request

  if (!pull) {
    core.info('No pull_request payload found; skipping review post.')
    return
  }

  const files = await github.paginate(github.rest.pulls.listFiles, {
    owner: context.repo.owner,
    repo: context.repo.repo,
    pull_number: pull.number,
    per_page: 100,
  })

  const changedLinesByPath = new Map(
    files.map((file) => [file.filename, parseChangedLines(file.patch)]),
  )

  const inlineComments = []
  const summaryOnlyFindings = []

  const maxInlineComments = Number(config.maxInlineComments || 20)

  for (const finding of report.findings || []) {
    const changedLines = changedLinesByPath.get(finding.path)

    if (
      changedLines?.has(finding.line) &&
      inlineComments.length < maxInlineComments
    ) {
      inlineComments.push({
        path: finding.path,
        line: finding.line,
        side: 'RIGHT',
        body: formatFinding(finding),
      })
    } else {
      summaryOnlyFindings.push(finding)
    }
  }

  const blockingSeverities = new Set(
    config.blockingSeverities || ['blocker', 'high'],
  )
  const shouldRequestChanges = (report.findings || []).some(
    (finding) =>
      blockingSeverities.has(finding.severity) || finding.should_block_merge,
  )
  const decision = normalizeDecision(report, shouldRequestChanges)
  // Non-blocking findings do not gate merges (the workflow files them as
  // issues), so a 'comment' decision submits an APPROVE review: GitHub only
  // supersedes a reviewer's earlier changes-requested review on approval or
  // explicit dismissal, and a lingering COMMENT would leave reviewDecision
  // stuck at CHANGES_REQUESTED forever even after every finding is fixed.
  const reviewEvent =
    decision === 'request_changes' ? 'REQUEST_CHANGES' : 'APPROVE'

  let submittedReviewEvent = reviewEvent
  let reviewFallbackNote = ''

  try {
    const reviewBody =
      decision === 'comment'
        ? `${report.summary}\n\nNon-blocking findings are posted inline and tracked as issues; approving per repository merge policy.`
        : report.summary

    const reviewPayload = {
      owner: context.repo.owner,
      repo: context.repo.repo,
      pull_number: pull.number,
      commit_id: pull.head.sha,
      event: reviewEvent,
      body: reviewBody,
    }

    if (inlineComments.length > 0) {
      reviewPayload.comments = inlineComments
    }

    await github.rest.pulls.createReview(reviewPayload)
  } catch (error) {
    if (reviewEvent !== 'APPROVE') {
      throw error
    }

    submittedReviewEvent = 'COMMENT'
    reviewFallbackNote =
      'GitHub did not allow this workflow to approve the PR. Enable repository workflow permission `Allow GitHub Actions to create and approve pull requests` if approvals should be posted by the bot.'
    core.warning(reviewFallbackNote)

    const fallbackPayload = {
      owner: context.repo.owner,
      repo: context.repo.repo,
      pull_number: pull.number,
      commit_id: pull.head.sha,
      event: 'COMMENT',
      body: `${report.summary}\n\n${reviewFallbackNote}`,
    }

    if (inlineComments.length > 0) {
      fallbackPayload.comments = inlineComments
    }

    await github.rest.pulls.createReview(fallbackPayload)
  }

  const counts = (report.findings || []).reduce((acc, finding) => {
    acc[finding.severity] = (acc[finding.severity] || 0) + 1
    return acc
  }, {})

  const countText =
    Object.entries(counts)
      .map(([severity, count]) => `${severity}: ${count}`)
      .join(', ') || 'none'

  const summaryLines = [
    marker,
    '## 🤖 Codex Review Summary',
    '',
    report.summary,
    '',
    '| Item | Result |',
    '| --- | --- |',
    `| 🧭 Review event | **${decisionLabel(decision)}** |`,
    `| 📬 Submitted as | **${decisionLabel(submittedReviewEvent.toLowerCase())}** |`,
    `| 🔎 Findings after threshold filtering | ${countText} |`,
    `| 💬 Inline comments posted | ${inlineComments.length} |`,
  ]

  if (reviewFallbackNote) {
    summaryLines.push('', `⚠️ Note: ${reviewFallbackNote}`)
  }

  if (summaryOnlyFindings.length > 0) {
    summaryLines.push('', '📌 Findings that could not be anchored inline:')
    for (const finding of summaryOnlyFindings) {
      summaryLines.push(
        `- **${finding.severity}/${finding.category}** ${finding.path}:${finding.line || '?'} - ${finding.title}: ${finding.body}`,
      )
    }
  }

  if (!report.findings?.length) {
    summaryLines.push('', '✅ No findings met the configured review threshold.')
  }

  const body = summaryLines.join('\n')
  const comments = await github.paginate(github.rest.issues.listComments, {
    owner: context.repo.owner,
    repo: context.repo.repo,
    issue_number: pull.number,
    per_page: 100,
  })

  const existing = comments.find(
    (comment) => comment.user?.type === 'Bot' && comment.body?.includes(marker),
  )

  if (existing) {
    await github.rest.issues.updateComment({
      owner: context.repo.owner,
      repo: context.repo.repo,
      comment_id: existing.id,
      body,
    })
  } else {
    await github.rest.issues.createComment({
      owner: context.repo.owner,
      repo: context.repo.repo,
      issue_number: pull.number,
      body,
    })
  }
}
