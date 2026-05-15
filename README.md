# Meeting Scheduling Agent

A LangGraph-based scheduling agent that can read email threads, identify meeting requests, check availability, propose meeting times, and route calendar/email actions through an approval step.

The project starts with mock email and calendar integrations so you can run the workflow locally before connecting Gmail, Google Calendar, Outlook, or Microsoft Graph.

## What This Agent Does

- Classifies incoming email threads as scheduling, rescheduling, cancellation, or not scheduling.
- Extracts meeting duration, attendees, date windows, and basic constraints.
- Checks busy blocks across attendees.
- Applies scheduling preferences such as business hours, buffers, preferred days, and blackout periods.
- Drafts a scheduling response with ranked time options.
- Uses a human approval gate before sending or creating external side effects.
- Leaves clear integration seams for real email and calendar APIs.

## Project Layout

```text
meeting-scheduling-agent/
  docs/
    architecture.md
  src/
    meeting_scheduler_agent/
      cli.py
      config.py
      graph.py
      mock_integrations.py
      models.py
      preferences.py
      prompts.py
      state.py
      tools.py
  tests/
    test_slot_ranking.py
  pyproject.toml
```

## Quick Start

```powershell
cd meeting-scheduling-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
meeting-scheduler-agent demo
```

If you prefer not to install the console script yet:

```powershell
python -m meeting_scheduler_agent.cli demo
```

## Next Integrations

Replace the mock clients in `mock_integrations.py` with implementations of the protocols in `tools.py`.

Good first production integrations:

- Gmail or Microsoft Graph email thread reader.
- Google Calendar or Outlook availability lookup.
- Contact lookup for account ownership, CRM metadata, and timezone hints.
- Persistent checkpointer for long-running threads.
- LangSmith tracing for debugging agent runs.

## Approval Model

The default graph supports an approval node. During local demos, `auto_approve=True` keeps the flow simple. In production, keep approval enabled for:

- Sending external emails.
- Creating, updating, or canceling calendar invites.
- Booking outside business hours.
- Overriding blackout periods or VIP account rules.
