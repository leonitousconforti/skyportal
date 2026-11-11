/**
 * Client construction, envelope unwrapping and error handling.
 *
 * Every SkyPortal response is wrapped by `BaseHandler.success`/`error` as
 * `{ status, message, data, version }` with HTTP 200 even for application-level
 * errors, so success is decided by `status`, not by the status code.
 */
import * as v from "valibot";

/**
 * The part of `fetch` this client uses. Narrower than `typeof fetch` so that a
 * plain wrapper function -- the usual way to attach an abort signal -- is a
 * valid replacement.
 */
export type FetchLike = (url: string, init: RequestInit) => Promise<Response>;

/** Options accepted by {@link createClient}. */
export interface ClientOptions {
  /** API token. Omit for cookie authentication or anonymous access. */
  token?: string | undefined;
  /** Extra headers sent with every request. */
  headers?: Record<string, string> | undefined;
  /** Per-request timeout in milliseconds; `null` disables it. */
  timeout?: number | null | undefined;
  /** Replacement `fetch`, for wiring an abort signal or credentials per call. */
  fetch?: FetchLike | undefined;
}

/** A value a query parameter can take. Arrays are sent as a repeated key. */
export type QueryValue =
  | string
  | number
  | boolean
  | null
  | undefined
  | readonly (string | number | boolean)[];

export type QueryParams = Record<string, QueryValue>;

/** Raised when SkyPortal answers with an error envelope or a non-JSON body. */
export class SkyPortalError extends Error {
  readonly statusCode: number | undefined;

  constructor(message: string, statusCode?: number | undefined) {
    super(message);
    this.name = "SkyPortalError";
    this.statusCode = statusCode;
  }
}

/**
 * Raised when a response does not match its model.
 *
 * The offending `payload` rides along so an application can log the drift and
 * decide for itself whether to carry on: a server that adds a column should not
 * be able to take a page down.
 */
export class SkyPortalValidationError extends Error {
  readonly issues: readonly [v.BaseIssue<unknown>, ...v.BaseIssue<unknown>[]];
  readonly payload: unknown;

  constructor(
    model: string,
    issues: readonly [v.BaseIssue<unknown>, ...v.BaseIssue<unknown>[]],
    payload: unknown,
  ) {
    super(`${model} does not understand: ${issues.map(describe).join("; ")}`);
    this.name = "SkyPortalValidationError";
    this.issues = issues;
    this.payload = payload;
  }
}

function describe(issue: v.BaseIssue<unknown>): string {
  const path = issue.path?.map((segment) => String(segment.key)).join(".");
  return path ? `${path}: ${issue.message}` : issue.message;
}

/**
 * Decode `data` with `schema`, or throw {@link SkyPortalValidationError}.
 *
 * `model` names the schema in the error. A valibot schema does not carry its
 * own name, and the name is what turns "a page failed to render" into "the
 * server added a column to Comment".
 */
export function parse<TSchema extends v.GenericSchema>(
  schema: TSchema,
  data: unknown,
  model: string,
): v.InferOutput<TSchema> {
  const result = v.safeParse(schema, data);
  if (!result.success) {
    throw new SkyPortalValidationError(model, result.issues, data);
  }
  return result.output;
}

function queryString(params: QueryParams | undefined): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue;
    if (Array.isArray(value)) {
      for (const item of value) search.append(key, String(item));
    } else {
      search.append(key, String(value));
    }
  }
  const rendered = search.toString();
  return rendered ? `?${rendered}` : "";
}

export interface RequestOptions {
  query?: QueryParams | undefined;
  body?: unknown;
}

/** A configured SkyPortal connection. Endpoint functions take one as their first argument. */
export interface SkyPortalClient {
  readonly baseUrl: string;
  /** Send a request and return the envelope's `data`. */
  request(
    method: string,
    path: string,
    options?: RequestOptions,
  ): Promise<unknown>;
  /** Send a request and return the raw response, for endpoints that send a file. */
  requestRaw(
    method: string,
    path: string,
    options?: RequestOptions,
  ): Promise<Response>;
}

/**
 * Build a client for the SkyPortal instance at `baseUrl`.
 *
 * `token` is optional: in a browser served by SkyPortal itself, the session
 * cookie authenticates the request.
 */
export function createClient(
  baseUrl: string,
  options: ClientOptions = {},
): SkyPortalClient {
  const root = baseUrl.replace(/\/+$/, "");
  const doFetch: FetchLike =
    options.fetch ?? ((url, init) => globalThis.fetch(url, init));
  const timeout = options.timeout === undefined ? 30_000 : options.timeout;

  async function send(
    method: string,
    path: string,
    requestOptions: RequestOptions = {},
  ): Promise<Response> {
    const headers: Record<string, string> = { ...options.headers };
    if (options.token) headers["Authorization"] = `token ${options.token}`;
    if (requestOptions.body !== undefined) {
      headers["Content-Type"] = "application/json";
    }
    const init: RequestInit = { method, headers, credentials: "same-origin" };
    if (requestOptions.body !== undefined) {
      init.body = JSON.stringify(requestOptions.body);
    }
    if (timeout !== null) init.signal = AbortSignal.timeout(timeout);
    return doFetch(`${root}${path}${queryString(requestOptions.query)}`, init);
  }

  return {
    baseUrl: root,
    requestRaw: send,
    async request(method, path, requestOptions) {
      return unwrap(await send(method, path, requestOptions));
    },
  };
}

/** Return an envelope's `data`, or throw {@link SkyPortalError}. */
export async function unwrap(response: Response): Promise<unknown> {
  let payload: { status?: string; message?: string; data?: unknown };
  try {
    payload = (await response.json()) as typeof payload;
  } catch {
    throw new SkyPortalError(
      `SkyPortal returned a non-JSON response (HTTP ${response.status})`,
      response.status,
    );
  }
  if (response.ok && payload.status === "success") return payload.data;
  throw new SkyPortalError(
    payload.message || `HTTP ${response.status}`,
    response.status,
  );
}
