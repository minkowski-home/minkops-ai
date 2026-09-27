# Workflows

Place shared Python business workflows here when more than one application or
solution needs the same implementation. A workflow owns its input/output
contract and business sequence, and may combine deterministic code, model
calls, and connector tools.

Keep a one-caller workflow with its application or client solution until reuse
is real. Put client mappings, policies, and overrides in `solutions/<id>/`.
Keep one-off model instructions beside the workflow. This directory does not
imply an agent, skill, capabilities layer, or generic step framework.
