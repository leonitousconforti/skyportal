/** First-party JavaScript client for the SkyPortal API. */
import * as groups from "./groups.js";
import * as sources from "./sources.js";
import {
  createClient as createBaseClient,
  type ClientOptions,
} from "./http.js";

export * from "./groups.js";
export * from "./http.js";
export * from "./sources.js";
export * as models from "./models/index.js";

const endpoints = { ...groups, ...sources };

/** Every endpoint function, bound to a client as a method. */
export type SkyPortal = ReturnType<typeof createClient>;

/**
 * Build a client for the SkyPortal instance at `baseUrl`, with every endpoint
 * function bound as a method.
 *
 * `client.fetchGroup(1)` and `fetchGroup(client, 1)` are the same call: the
 * bound methods exist so a client reads like an object, the plain functions so
 * a bundler can drop the ones an application never uses.
 */
export function createClient(baseUrl: string, options: ClientOptions = {}) {
  const client = createBaseClient(baseUrl, options);
  const bound = Object.fromEntries(
    Object.entries(endpoints).map(([name, endpoint]) => [
      name,
      (...args: unknown[]) =>
        (endpoint as (...rest: unknown[]) => unknown)(client, ...args),
    ]),
  ) as {
    [K in keyof typeof endpoints]: (typeof endpoints)[K] extends (
      client: never,
      ...args: infer A
    ) => infer R
      ? (...args: A) => R
      : never;
  };
  return { ...client, ...bound };
}
