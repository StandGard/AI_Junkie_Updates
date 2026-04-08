"""Context prompt injected into Claude analysis for regulatory items."""

AGENT_CONTEXT_PROMPT = """
Source type: Regulatory filing or government document
This content comes from a government agency, regulatory body, or legislative source — such as the FTC, EU AI Office, NIST, UK DSIT, Congress, or equivalent international bodies. When analyzing it:
COLLECT if the document:

Is a new law, regulation, or executive order that affects AI development, deployment, or commercialisation
Is an enforcement action, fine, investigation, or legal proceeding targeting an AI company
Is a significant policy consultation, draft regulation, or proposed rule with meaningful scope
Is a government report or assessment that changes the policy landscape for AI
Represents a country or major jurisdiction announcing a new AI strategy, investment, or programme
Is a court ruling that has implications for AI liability, copyright, or data use

IGNORE if the document:

Is a routine administrative filing with no policy implications
Is a minor procedural update to an existing regulation
Is a low-level government communication with no substantive AI policy content
Is a press release from a politician without a corresponding legislative action
Is academic or advisory in nature with no binding effect

Regulatory developments move slowly but matter enormously. Surface anything with real teeth.
"""
