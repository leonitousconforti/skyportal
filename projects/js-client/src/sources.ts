/** Typed endpoint functions for `/api/sources`. */
import {
  SourcePostResponseSchema,
  SourceResponseSchema,
  SourcesPageResponseSchema,
  type SourceGetQuery,
  type SourcePatchBody,
  type SourcePostBody,
  type SourcePostResponse,
  type SourceResponse,
  type SourcesPageResponse,
} from "./models/sources.js";
import { parse, type SkyPortalClient } from "./http.js";

export type {
  SourceGetQuery,
  SourcePatchBody,
  SourcePostBody,
  SourcePostResponse,
  SourceResponse,
  SourcesPageResponse,
};

/**
 * Retrieve a single source by object ID.
 *
 * The `include*` flags each pull in an extra body of data (photometry,
 * thumbnails, classifications ...); leaving them off keeps the response small.
 */
export async function fetchSource(
  client: SkyPortalClient,
  objId: string,
  query: SourceGetQuery = {},
): Promise<SourceResponse> {
  const data = await client.request("GET", `/api/sources/${objId}`, { query });
  return parse(SourceResponseSchema, data, "SourceResponse");
}

/**
 * Query sources, one page at a time.
 *
 * `query` is the endpoint's own parameter model, so its keys are the wire
 * spellings the handler reads (`pageNumber`, `numPerPage`, `TNSname`, ...)
 * rather than a second set of names this client would have to keep in step.
 */
export async function fetchSources(
  client: SkyPortalClient,
  query: SourceGetQuery = {},
): Promise<SourcesPageResponse> {
  const data = await client.request("GET", "/api/sources", { query });
  return parse(SourcesPageResponseSchema, data, "SourcesPageResponse");
}

/**
 * Save a source.
 *
 * `id` names the object; an object that already exists is saved to the given
 * groups rather than created afresh.
 */
export async function postSource(
  client: SkyPortalClient,
  payload: SourcePostBody,
): Promise<SourcePostResponse> {
  const data = await client.request("POST", "/api/sources", { body: payload });
  return parse(SourcePostResponseSchema, data, "SourcePostResponse");
}

/** Update a source's object columns. Omitted fields are left unchanged. */
export async function updateSource(
  client: SkyPortalClient,
  objId: string,
  payload: SourcePatchBody,
): Promise<void> {
  await client.request("PATCH", `/api/sources/${objId}`, { body: payload });
}

/** Unsave a source from one group. */
export async function deleteSource(
  client: SkyPortalClient,
  objId: string,
  groupId: number,
): Promise<void> {
  await client.request("DELETE", `/api/sources/${objId}`, {
    body: { group_id: groupId },
  });
}
