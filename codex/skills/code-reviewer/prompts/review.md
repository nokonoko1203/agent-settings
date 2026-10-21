<task>
Use $code-reviewer to review the provided PR, diff, commit, or file set.
</task>

<review_contract>
Prioritize material findings over summary.
Use the fixed output order:
1. Findings
2. Coverage gaps
3. Architecture notes
4. Open questions
5. Change summary
6. Residual risks
</review_contract>

<focus>
Target: {{TARGET_LABEL}}
Focus: {{USER_FOCUS}}
</focus>

<repository_context>
{{REVIEW_INPUT}}
</repository_context>
