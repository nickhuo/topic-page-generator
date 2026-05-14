# Issue tracker: Linear

Issues and PRDs for this repo live in **Linear**, in team `DEV`, project `topic-page-generator`. All operations go through the Linear MCP tools (`mcp__claude_ai_Linear__*`). Do not use the `linear` CLI.

## Scope identifiers

- **Team key**: `DEV`
- **Project name**: `topic-page-generator`

Resolve the team ID with `list_teams` (filter by key=`DEV`) and the project ID with `list_projects` (filter by team + name). Cache these for the session.

## Conventions

- **Create an issue**: `save_issue` with `teamId`, `projectId`, `title`, `description`. Use multi-line markdown in `description` — Linear renders it.
- **Read an issue**: `get_issue` by id or identifier (e.g. `DEV-123`). Pair with `list_comments` for the discussion thread.
- **List issues**: `list_issues` filtered by `teamId` and/or `projectId`; add `stateType` for status filters, `labelIds` for label filters.
- **Comment on an issue**: `save_comment` with `issueId` and `body`.
- **Apply / remove labels**: `save_issue` with the updated `labelIds` array (Linear updates labels by replacing the full set). Use `list_issue_labels` to resolve label names → IDs.
- **Change status**: `save_issue` with `stateId` (resolve via `list_issue_statuses`).
- **Close**: set the issue's `stateId` to the `completed` or `canceled` state for team `DEV`.

## When a skill says "publish to the issue tracker"

Create a Linear issue via `save_issue` scoped to team `DEV` + project `topic-page-generator`.

## When a skill says "fetch the relevant ticket"

Run `get_issue` with the identifier (e.g. `DEV-42`) and `list_comments` on the same issue.
