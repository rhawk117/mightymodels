---
paths:
  - "src/api/**/*.ts"
---

<scope>
Governs the HTTP handlers under src/api when an agent creates, edits or reviews them. Does not cover the generated client.
</scope>

<conventions>
1. Return the shared error envelope from `src/api/errors.ts`, which defines the only shape consumers parse.
</conventions>

<examples>
Error response:

```ts
return errorEnvelope(404, 'order not found');
```

</examples>

<anti_patterns>

- Building an error object inline; return the shared envelope instead.
</anti_patterns>

<verification>
Before finishing a change to a handler, run `npm test`. A reviewer can confirm by calling the endpoint with bad input.
</verification>
