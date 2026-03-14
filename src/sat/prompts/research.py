"""Prompts for deep research query generation and evidence structuring.

@decision DEC-PROMPT-RES-001: Research prompts co-located with pipeline modules.
@title Research prompts kept minimal in prompts package
@status accepted
@rationale The query generation and structuring prompts live in the research
package (runner.py and structurer.py) since they are tightly coupled to those
modules. This file provides the namespace for consistency with other prompt modules.
"""

# Research prompts are defined inline in:
#   - research/runner.py (QUERY_SYSTEM_PROMPT for query generation)
#   - research/structurer.py (STRUCTURER_SYSTEM_PROMPT for evidence structuring)
# This is intentional — those prompts are tightly coupled to their pipeline steps.
