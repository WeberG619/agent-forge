Display a comprehensive list of all available Claude Skills.

Show the following information:

## Available Skills
For each .skill file in the skills directory:
- Skill filename
- Primary purpose (infer from name)
- Example trigger phrase

## Quick Info
- Skills are ZIP archives containing a SKILL.md and reference files
- Skills work in Web Claude.ai (upload at claude.ai/settings)
- They can also be used in Claude Code via the `/use-skill` command
- Skills activate automatically via natural language when uploaded

## How to Use
- Upload: Go to https://claude.ai/settings -> Skills
- In CLI: `/use-skill [skill-name]`
- View details: `/skill-info [skill-name]`
