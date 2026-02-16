# Task Queue Management

Manage project task queues with organized tracking.

## How to Use

When the user invokes `/tasks`, help them manage their task queues using Claude Code's built-in TaskCreate, TaskUpdate, and TaskList tools.

### Available Operations

**View all tasks:**
Use TaskList to show current tasks and their status.

**Add a task:**
Use TaskCreate with a clear subject and description.

**Update a task:**
Use TaskUpdate to change status (pending → in_progress → completed).

**Set dependencies:**
Use TaskUpdate with addBlockedBy to define task ordering.

### Workflow

1. User provides a list of tasks they want done
2. Create the task queue with TaskCreate for each
3. Set up dependencies with addBlockedBy
4. Show them the status with TaskList
5. Work through tasks in dependency order
6. Mark completed as you finish each one

### Best Practices

- Keep task subjects in imperative form ("Fix auth bug", "Add tests")
- Include enough description for another agent to understand
- Set activeForm for progress display ("Fixing auth bug")
- Prefer working on tasks in ID order
- Mark tasks in_progress before starting
