"""Meeting summarization using Claude API."""

import logging

import anthropic

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """You are analyzing a meeting transcript. Please provide a structured summary.

Start with a single line in exactly this format (2-5 words, no punctuation):
**Topic:** <short topic title>

Then include the following sections:

## Key Points
List the main topics discussed and important information shared (3-7 bullet points).

## Action Items
List any tasks, assignments, or follow-ups mentioned. Format as checkboxes:
- [ ] Task description (assigned to: person, if mentioned)

## Decisions Made
List any decisions that were reached during the meeting.

## Participants
If you can identify speakers or attendees mentioned, list them here.

## Notes
Any other important context or observations.

Keep the summary concise but comprehensive. Use bullet points for readability.

Here is the transcript:

{transcript}"""


class Summarizer:
    """Summarizes meeting transcripts using Claude API."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        if not api_key:
            raise ValueError(
                "Anthropic API key required. Set ANTHROPIC_API_KEY environment variable "
                "or add to ~/.config/meetcap/config.yaml"
            )
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def summarize(self, transcript: str) -> str:
        """
        Generate a summary of the meeting transcript.

        Args:
            transcript: The full meeting transcript text

        Returns:
            Formatted markdown summary
        """
        logger.info("Generating meeting summary with Claude...")

        # Truncate very long transcripts to stay within context limits
        max_chars = 100000  # ~25k tokens, leaving room for response
        if len(transcript) > max_chars:
            logger.warning(f"Transcript truncated from {len(transcript)} to {max_chars} chars")
            transcript = transcript[:max_chars] + "\n\n[Transcript truncated due to length...]"

        message = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": SUMMARY_PROMPT.format(transcript=transcript),
                }
            ],
        )

        return message.content[0].text


def summarize_transcript(transcript: str, api_key: str) -> str:
    """Convenience function to summarize a transcript."""
    summarizer = Summarizer(api_key=api_key)
    return summarizer.summarize(transcript)
