"""Context prompt injected into Claude analysis for GitHub items."""

AGENT_CONTEXT_PROMPT = """
Source type: GitHub repository release or event
This content comes from a GitHub repository — either a new release, a significant commit, or a repository event. When analyzing it:
COLLECT if the release:

Is a new open-source AI model, framework, or tool reaching a stable or public release
Represents a major version milestone for a widely-used AI library or tool
Introduces a new architecture, training technique, or inference approach
Is a first public release of a project from a known AI lab or prominent researcher
Includes model weights, training code, or evaluation benchmarks
Is a significant release of AI infrastructure tooling (serving frameworks, fine-tuning tools, evaluation harnesses)

IGNORE if the release:

Is a patch release for a project with limited adoption
Is a minor update to an existing project with no new capabilities
Is from an unknown repository with no stars or community engagement
Is documentation-only or contains no functional changes
Is a fork of an existing project without substantial modifications

GitHub is the ground truth for open-source AI. Surface releases that the community will care about.
"""
