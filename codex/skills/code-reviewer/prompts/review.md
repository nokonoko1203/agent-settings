<task>
Use $code-reviewer to review the provided PR, diff, commit, or file set.
</task>

<review_contract>
Prioritize material findings over summary.
Follow references/output-template.md. For each PR (or target), use the fixed order:
1. Link
2. Title
3. Summary (1-3 sentences)
4. Findings (P0-P3, highest first)
Add impact analysis, notes, and coverage only after the findings, and only when they matter for the decision.
Write the full review in this form in the chat reply as well; never condense it into a table and defer the details to a file.
The reader must understand what the PR does, what is wrong, and how to fix it from this text alone, without opening the diff.
</review_contract>

<focus>
Target: {{TARGET_LABEL}}
Focus: {{USER_FOCUS}}
</focus>

<repository_context>
{{REVIEW_INPUT}}
</repository_context>
