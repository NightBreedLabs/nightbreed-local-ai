# Security

Do not report exploitable vulnerabilities in a public GitHub issue with sensitive proof-of-concept data. Contact the repository maintainer through GitHub's private vulnerability reporting mechanism if the project has it enabled.

This toolkit intentionally communicates with Ollama over a loopback HTTP endpoint and does not open a server port. It can index local files and store a private imported knowledge base under `~/.local/share/nbai/`. Those files should never be committed to GitHub or pasted into issues. MCP calls from a cloud-connected IDE can disclose tool prompts/results to that IDE's provider; local inference alone is not end-to-end confidentiality.

Before sharing diagnostics, redact usernames, paths revealing private information, IP addresses, hostnames, tokens, and indexed content. If you discover an accidental secret commit, revoke the secret immediately; removing it from the current branch does not erase Git history.
