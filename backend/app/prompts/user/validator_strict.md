# Claim narrative

{claim_narrative}

# Retrieved policy chunks

The following chunks were retrieved from the carrier's commercial property policy by cosine-similarity search against the narrative above. They are the **only** authority you may cite.

{retrieved_chunks}

# Task — strict review

Decide whether the policy covers the loss described in the narrative, applying a **stricter standard** than the baseline review:

- Treat a cause as covered **only** when the retrieved chunks contain language that affirmatively names or describes it as a covered peril. Silence is not coverage: if the chunks do not positively establish cover, set `covered=false`.
- Hold confidence down unless the policy-language match is unambiguous. A partial, inferred, or analogical match is mid-to-low confidence, not high.
- Cite **only** chunks whose text you actually relied on; do not pad `cited_chunks`. Every cited `chunk_id` must be one supplied above — a citation to anything else is a hard error the caller rejects.
- Never reference an endorsement, sub-limit, exclusion, or definition that is not present verbatim in the retrieved chunks.

Return the JSON object specified in your system instructions — no preamble, no Markdown fencing, no trailing prose.
