Explain, in plain language for a claims manager, why claim {claim_id} settled or was sent to a person. Use only the claims MCP server's tools and only what they return.

1. Call `get_claim` with the claim id to get the claim and its runs. Use the most recent completed run.
2. Call `explain_decision` with that run's correlation id.
3. Answer in a short paragraph: what the claim was, whether the policy covered it and why, what settlement was proposed and whether it sat inside the expected range, whether the Guardrail objected to anything and whether any objection counted, and which escalation rules fired (name each rule and the value it observed) or that none did.
4. If the Guardrail discarded a model claim, say what the model claimed and why the code refused it, in one sentence.
5. End with the audit row ids your answer rests on, and say that the whole-ledger chain check can be run with `verify_chain`.
