# dot-claude

## Commands

### `/commit`

Analyzes staged changes and creates a [Conventional Commits](https://www.conventionalcommits.org) message.

```
/commit [file ...]
```

- Optionally accepts files to stage; if other related files are detected, asks before including them
- Detects Jira ticket from branch config or branch name for the scope
- Detects whether staged changes form a single cohesive change or multiple unrelated ones, and lists unrelated changes as bullets in the body
- Reviews staged changes and suggests improvements before generating the commit message
  - Flags DRY violations (duplicated logic, repeated literals, copy-pasted blocks); test code is exempt since tests favor DAMP over DRY
  - Flags tests with cyclomatic complexity greater than one, recommending the branching logic be extracted into a named function and covered via `/unit-test`
- Generates 3 candidate commit messages and picks the best one
- Asks for the rationale and incorporates it into the commit body
- Updates `README.md` when the change affects UX, and stages it automatically
- Shows a summary of staged/unstaged/untracked files and confirms before committing

### `/unit-test`

Generates unit tests for functions in the specified source files.

```
/unit-test <file> [file ...]
```

- Identifies functions with branching logic and generates tests aimed at exercising each independent condition
- Detects and matches the project's existing test framework and conventions; asks if none can be detected
- Proposes minimal testability refactors (e.g. dependency injection, splitting pure logic from I/O) and asks before applying them
- Names tests by input scenario and expected outcome, without referencing internal coverage terminology
- Runs the test suite after generation and reports which functions got tests, which were skipped, and the test command's result
