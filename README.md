# dot-claude

## Commands

### `/commit`

Analyzes staged changes and creates a [Conventional Commits](https://www.conventionalcommits.org) message.

- Detects Jira ticket from branch config or branch name for the scope
- Generates 3 candidate commit messages and picks the best one
- Asks for your rationale and incorporates it into the commit body
- Updates `README.md` when the change affects UX, and stages it automatically
- Shows a summary of staged/unstaged/untracked files and confirms before committing
