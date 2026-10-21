<task>
Use $code-reviewer to review this change with extra weight on architecture consistency.
</task>

<review_focus>
Check layer boundaries, responsibility separation, contract and side-effect separation, dependency direction, and whether tests exercise the real production path.
Still report concrete bugs and coverage gaps first if they exist.
</review_focus>

<target>
Scope: {{TARGET_LABEL}}
Architecture concern: {{USER_FOCUS}}
</target>

<repository_context>
{{REVIEW_INPUT}}
</repository_context>
