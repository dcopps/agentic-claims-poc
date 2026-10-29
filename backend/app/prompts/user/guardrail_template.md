# Adjuster output

- Recommended settlement (USD): {adjuster_settlement}
- Reasoning:

{adjuster_reasoning}

# Retrieved policy chunks

{retrieved_chunks}

# Pre-detected findings (do not duplicate)

{rule_flags_already_found}

# Task

Apply your system instructions to the adjuster's reasoning above. For citations: first list every policy provision the reasoning names by title or number; flag only those absent from the retrieved chunks. Settlement-method vocabulary, severity or market bands and descriptions of the peril are not citations and are not flagged. Also report PII leakage and bias not already raised by the rule engine. Return the JSON object specified in your system instructions — `flags: []` if nothing new was found.
