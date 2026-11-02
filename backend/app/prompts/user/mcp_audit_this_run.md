Audit pipeline run {correlation_id} using the claims MCP server. Use only what the tools return; do not infer anything the record does not state.

1. Call `verify_chain` with the correlation id and report whether the audit ledger verifies, how many rows were checked, and that the check is whole-ledger (the run's rows cannot be verified in isolation).
2. Call `explain_decision` with the correlation id. Report, in this order, citing the audit row id of each:
   - the outcome (settled, awaiting a person, or aborted) and the settlement figure if there is one;
   - the Validator's verdict, its confidence, and the policy passages it saw and cited;
   - the Adjuster's recommended figure, the range it was held to, and its reasoning;
   - the Guardrail's result: the rule-engine findings, the model claims that were counted, and the model claims that were discarded, giving the model's quoted words beside the code's reason for refusing each;
   - the escalation rules that fired, or that none did;
   - any human decision recorded.
3. Call `get_audit_trail` with the correlation id and `include_prompts` false, and confirm that the rows you cited exist in chain order.
4. Close with one sentence on whether the record supports the outcome, and name anything the record does not contain.
