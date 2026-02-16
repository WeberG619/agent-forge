Display detailed information about a specific Claude Skill file.

Ask the user which skill they want to examine (or they can provide it directly).

Then:

1. **Locate the skill file** in the skills/ directory

2. **Extract and display contents** (.skill files are ZIP archives):
   - Extract to /tmp/skill-extraction/
   - Display the SKILL.md contents (main skill definition)
   - List all reference files in references/ folder
   - Show file sizes

3. **Provide usage information**:
   - Trigger phrases from the skill metadata
   - Best use cases
   - How to upload (if not already uploaded)

4. **Clean up** temporary extraction folder
