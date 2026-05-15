# Architecture

## Core Flow

```mermaid
flowchart TD
  A["Email thread received"] --> B["Classify intent"]
  B -->|Not scheduling| Z["Ignore / normal reply"]
  B -->|New meeting| C["Extract request"]
  B -->|Reschedule| R["Load existing event"]
  B -->|Cancel| X["Cancel / update event"]

  C --> D["Resolve people, time zones, preferences"]
  R --> D
  D --> E["Check calendar availability"]
  E --> F["Rank candidate slots"]
  F --> G["Draft response or invite"]
  G --> H["Human approval gate"]
  H -->|Approve| I["Send email / create invite"]
  H -->|Edit| G
  H -->|Reject| Z
  I --> J["Wait for replies"]
  J --> B
```

In code, `load_email_thread` represents the incoming email-thread event before classification.
For the local mock demo, `wait_for_replies` marks the state as waiting and then terminates through the not-scheduling path so the run does not reprocess the same email forever. In production, resume the graph from this node when a new email reply arrives.

## State

The graph uses a shared scheduling state with:

- `email_thread_id`
- `email_thread`
- `intent`
- `existing_event`
- `meeting_request`
- `participants`
- `timezones`
- `preference_summary`
- `busy_blocks`
- `candidate_slots`
- `selected_slot`
- `draft_reply`
- `approval`
- `calendar_event_id`
- `cancellation_result`
- `waiting_for_reply`
- `reply_received`
- `workflow_status`
- `error`

## Integration Boundary

Real providers should implement the protocols in `src/meeting_scheduler_agent/tools.py`.

The graph does not need to know whether availability came from Google Calendar, Outlook, or a mock object. This keeps the orchestration stable while integrations change.

## Production Notes

- Store all candidate slot calculations in UTC.
- Render times in the organizer and attendee time zones when drafting emails.
- Use a durable checkpointer for long-running email threads.
- Require approval for any action that sends an email or mutates a calendar.
- Add idempotency keys around send/create/update operations to prevent duplicate invites.
- Persist thread-to-event mappings so reschedules and cancellations can find the right event.
