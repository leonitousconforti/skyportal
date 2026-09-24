# skyportal-js

First-party JavaScript client for the [SkyPortal](https://skyportal.io) API.

```ts
import { createClient } from "skyportal-js";

const client = createClient("https://skyportal.example.org", { token });

const { user_groups } = await client.fetchGroups();
const source = await client.fetchSource("ZTF20abcdef", {
  includePhotometry: true,
});
```

Every endpoint is also a plain function taking the client first, so a bundler
can drop the ones an application never calls:

```ts
import { createClient, fetchSource } from "skyportal-js";

const source = await fetchSource(client, "ZTF20abcdef");
```

## Models

`src/models/` is generated from `projects/api-models`, the pydantic models the
server itself validates against. Run `make js-models` from the repository root
to regenerate, and do not edit it by hand. Each model becomes a valibot schema
plus its inferred type, so a response is checked against the same declaration
the handler documents.

Whether an unmodelled field is fatal comes from the pydantic model's
`model_config`: `extra="forbid"` becomes `v.strictObject` and rejects it,
`extra="ignore"` becomes `v.object` and drops it. `SkyPortalValidationError`
carries the offending payload so an application can log the drift and decide
for itself whether to carry on.

## Errors

- `SkyPortalError`: the API answered with an error envelope. `statusCode` is
  the HTTP status, which is 200 for most application-level errors.
- `SkyPortalValidationError`: the response did not match its model.
