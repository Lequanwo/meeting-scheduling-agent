from __future__ import annotations

import typer

from meeting_scheduler_agent.config import load_settings
from meeting_scheduler_agent.graph import build_graph
from meeting_scheduler_agent.mock_integrations import build_mock_tools
from meeting_scheduler_agent.preferences import default_preferences

app = typer.Typer(help="Run the meeting scheduling agent.")


@app.command()
def demo(thread_id: str = "thread-demo-1") -> None:
    """Run the agent against a mock email thread and mock calendar data."""
    settings = load_settings()
    tools = build_mock_tools(organizer_email=settings.organizer_email)
    preferences = default_preferences(
        organizer_email=settings.organizer_email,
        timezone_name=settings.timezone,
    )
    graph = build_graph(tools, preferences, auto_approve=True)

    result = graph.invoke(
        {"email_thread_id": thread_id},
        config={"configurable": {"thread_id": thread_id}},
    )

    typer.echo("\nIntent:")
    typer.echo(result.get("intent", "unknown"))
    typer.echo("\nDraft reply:")
    typer.echo(result.get("draft_reply", "No draft generated."))


if __name__ == "__main__":
    app()
