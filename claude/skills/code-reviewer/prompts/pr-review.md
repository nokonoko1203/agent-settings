<task>
Use $code-reviewer to review this pull request as a blocking code review.
</task>

<review_focus>
Treat bugs, regressions, contract violations, missing tests, and CI coverage gaps as the primary review surface.
Do not stop at the diff if surrounding code or architecture context is needed.
</review_focus>

<pull_request>
PR: {{PR_URL}}
Title: {{PR_TITLE}}
Author focus: {{USER_FOCUS}}
</pull_request>

<repository_context>
{{REVIEW_INPUT}}
</repository_context>
