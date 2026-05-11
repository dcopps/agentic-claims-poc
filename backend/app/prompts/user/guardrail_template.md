# Adjuster output

- Recommended settlement (USD): {adjuster_settlement}
- Reasoning:

{adjuster_reasoning}

# Retrieved policy chunks (the only authoritative source)

{retrieved_chunks}

# Pre-detected findings (do not duplicate)

{rule_flags_already_found}

# Task

Scan the adjuster's reasoning for additional PII leakage, hallucinated policy citations, and bias not already raised by the rule engine. Return the JSON object specified in your system instructions — `flags: []` if nothing new was found.
