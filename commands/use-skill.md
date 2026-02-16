Read and apply a specific Claude Skill framework.

Ask the user which skill they want to use (or they can specify it directly).

Available skills:
- idea-validator
- launch-planner
- product-manager
- product-designer
- marketing-writer
- email-drafter
- code-review-helper
- meeting-notes-processor

Then:
1. Extract the .skill file (ZIP archive) to a temp directory
2. Read the skill's SKILL.md file
3. Read any relevant reference files
4. Apply the framework to the user's task
5. Structure output according to the skill's guidelines
6. Clean up temp files

This allows skills to work directly in Claude Code without uploading to claude.ai.
