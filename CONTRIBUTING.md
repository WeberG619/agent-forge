# Contributing to Cadre

Thanks for your interest in contributing! Here's how to get started.

## Getting Started

1. Fork the repo
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/cadre-ai.git`
3. Create a branch: `git checkout -b my-feature`
4. Make your changes
5. Test on your machine with `./install.sh`
6. Commit and push
7. Open a Pull Request

## What to Contribute

- **New agents** — Add to `agents/` with a `.md` file following existing patterns
- **New slash commands** — Add to `commands/` with frontmatter + instructions
- **New MCP servers** — Add to `mcp-servers/` with a `requirements.txt` and `README.md`
- **Bug fixes** — Always welcome
- **Documentation** — Improvements to docs, examples, or inline comments
- **Cross-platform fixes** — macOS/Linux compatibility improvements

## Guidelines

- Keep changes focused — one feature or fix per PR
- Match existing code style
- Test your changes before submitting
- Update relevant docs if you change behavior
- Don't add external dependencies unless necessary

## Reporting Issues

Open an issue on GitHub with:
- What you expected to happen
- What actually happened
- Your OS and Python version
- Steps to reproduce

## License

By contributing, you agree that your contributions will be licensed under GPL-3.0.
