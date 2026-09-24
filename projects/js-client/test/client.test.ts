import { describe, expect, test } from "bun:test";

import {
  SkyPortalError,
  SkyPortalValidationError,
  createClient,
  fetchGroup,
  fetchGroups,
  fetchSources,
  postGroup,
} from "../src/index.js";

/** A client whose fetch answers with `payload`, recording the request it saw. */
function stubClient(payload: unknown, status = 200) {
  const seen: { url?: string; init?: RequestInit } = {};
  const client = createClient("https://sky.example.org/", {
    token: "abcd",
    fetch: async (url, init) => {
      seen.url = String(url);
      seen.init = init;
      return new Response(JSON.stringify(payload), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    },
  });
  return { client, seen };
}

const GROUP = {
  id: 1,
  name: "Test group",
  created_at: "2026-01-01T00:00:00",
  modified: "2026-01-01T00:00:00",
};

describe("createClient", () => {
  test("sends the token and unwraps the envelope", async () => {
    const { client, seen } = stubClient({
      status: "success",
      data: { user_groups: [GROUP], user_accessible_groups: [] },
      version: "1.4.0",
    });

    const groups = await fetchGroups(client);

    expect(seen.url).toBe(
      "https://sky.example.org/api/groups?includeSingleUserGroups=false",
    );
    expect(
      (seen.init?.headers as Record<string, string>)["Authorization"],
    ).toBe("token abcd");
    expect(groups.user_groups?.[0]?.name).toBe("Test group");
  });

  test("binds every endpoint as a method", async () => {
    const { client } = stubClient({ status: "success", data: GROUP });
    expect(await client.fetchGroup(1)).toEqual(await fetchGroup(client, 1));
  });

  test("turns an error envelope into a SkyPortalError", async () => {
    const { client } = stubClient({ status: "error", message: "Nope" }, 400);
    expect(fetchGroups(client)).rejects.toThrow(
      new SkyPortalError("Nope", 400),
    );
  });

  test("reports a non-JSON body rather than failing to parse it", async () => {
    const client = createClient("https://sky.example.org", {
      fetch: async () => new Response("<html>502</html>", { status: 502 }),
    });
    expect(fetchGroups(client)).rejects.toThrow(SkyPortalError);
  });
});

describe("response decoding", () => {
  test("rejects a field the model forbids, keeping the payload", async () => {
    const data = { ...GROUP, invented_column: 3 };
    const { client } = stubClient({ status: "success", data });

    try {
      await fetchGroup(client, 1);
      throw new Error("expected a validation error");
    } catch (error) {
      expect(error).toBeInstanceOf(SkyPortalValidationError);
      expect((error as SkyPortalValidationError).message).toStartWith(
        "GroupResponse does not understand: invented_column",
      );
      expect((error as SkyPortalValidationError).payload).toEqual(data);
    }
  });
});

describe("query parameters", () => {
  test("takes the endpoint's own wire spellings", async () => {
    const { client, seen } = stubClient({
      status: "success",
      data: { sources: [], totalMatches: 0 },
    });

    await fetchSources(client, {
      pageNumber: 2,
      numPerPage: 10,
      group_ids: [1, 2],
    });

    expect(seen.url).toBe(
      "https://sky.example.org/api/sources?pageNumber=2&numPerPage=10&group_ids=1&group_ids=2",
    );
  });

  test("omits parameters that were not given", async () => {
    const { client, seen } = stubClient({
      status: "success",
      data: { sources: [], totalMatches: 0 },
    });

    await fetchSources(client, { pageNumber: 1, TNSname: undefined });

    expect(seen.url).toBe("https://sky.example.org/api/sources?pageNumber=1");
  });

  test("rejects a parameter the endpoint does not read", async () => {
    const { client } = stubClient({
      status: "success",
      data: { sources: [], totalMatches: 0 },
    });
    // @ts-expect-error -- not a SourceGetQuery field
    await fetchSources(client, { pageNumbr: 1 }).catch(() => {});
  });
});

describe("request bodies", () => {
  test("posts JSON and decodes the created id", async () => {
    const { client, seen } = stubClient({ status: "success", data: { id: 7 } });

    const created = await postGroup(client, { name: "New group" });

    expect(seen.init?.method).toBe("POST");
    expect(seen.init?.body).toBe(JSON.stringify({ name: "New group" }));
    expect(created.id).toBe(7);
  });

  test("rejects a body field the model forbids", async () => {
    const { client } = stubClient({ status: "success", data: { id: 7 } });
    // @ts-expect-error -- not a GroupPost field
    await postGroup(client, { name: "New group", colour: "red" }).catch(
      () => {},
    );
  });
});
