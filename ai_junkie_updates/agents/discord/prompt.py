"""Context prompt injected into Claude analysis for Discord items."""

AGENT_CONTEXT_PROMPT = """
Source type: Discord server message
This content was received from a monitored Discord server — typically an AI company's official server, an open-source project community, or a researcher community. When analyzing it:
COLLECT if the message:

Is posted in an announcements or releases channel and contains a product or model update
Is from a verified staff or developer role and contains technical news or breaking information
Reports an outage, incident, or service degradation in a status channel
Announces a new feature, API change, or breaking change to developers
Contains a first announcement of a new open-source release or model drop
Is a staff member confirming or denying a rumour with material information

IGNORE if the message:

Is general community chat or off-topic discussion
Is a support request or technical help question
Is a meme, joke, or social interaction
Is speculative discussion among community members
Repeats information already announced elsewhere

Discord is often where companies communicate directly with developers. Surface the signal.
"""
