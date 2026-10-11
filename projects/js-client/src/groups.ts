/** Typed endpoint functions for `/api/groups`. */
import {
  GroupResponseSchema,
  type GroupMemberResponse,
  type GroupResponse,
  type GroupUserResponse,
} from "./models/_cyclic.js";
import {
  GroupPostResponseSchema,
  GroupStreamPostResponseSchema,
  GroupUserPostResponseSchema,
  GroupsResponseSchema,
  type GroupPost,
  type GroupPostResponse,
  type GroupStreamPostResponse,
  type GroupUserPostResponse,
  type GroupsResponse,
} from "./models/groups.js";
import { parse, type SkyPortalClient } from "./http.js";
import * as v from "valibot";

export type {
  GroupMemberResponse,
  GroupPost,
  GroupPostResponse,
  GroupResponse,
  GroupStreamPostResponse,
  GroupUserPostResponse,
  GroupUserResponse,
  GroupsResponse,
};

/** Retrieve the groups the token's user belongs to or can access. */
export async function fetchGroups(
  client: SkyPortalClient,
  options: { includeSingleUserGroups?: boolean } = {},
): Promise<GroupsResponse> {
  const data = await client.request("GET", "/api/groups", {
    query: {
      includeSingleUserGroups: options.includeSingleUserGroups ?? false,
    },
  });
  return parse(GroupsResponseSchema, data, "GroupsResponse");
}

/**
 * Retrieve a single group by ID.
 *
 * `includeGroupUsers` is on by default; pass false to skip the member list on
 * large groups.
 */
export async function fetchGroup(
  client: SkyPortalClient,
  groupId: number,
  options: { includeGroupUsers?: boolean } = {},
): Promise<GroupResponse> {
  const data = await client.request("GET", `/api/groups/${groupId}`, {
    query: { includeGroupUsers: options.includeGroupUsers ?? true },
  });
  return parse(GroupResponseSchema, data, "GroupResponse");
}

/** Retrieve the accessible groups with an exact name. */
export async function fetchGroupsByName(
  client: SkyPortalClient,
  name: string,
): Promise<GroupResponse[]> {
  const data = await client.request("GET", "/api/groups", { query: { name } });
  return parse(v.array(GroupResponseSchema), data, "GroupResponse[]");
}

/** Retrieve the server's configured public group. */
export async function fetchPublicGroup(
  client: SkyPortalClient,
): Promise<GroupResponse> {
  const data = await client.request("GET", "/api/groups/public");
  return parse(GroupResponseSchema, data, "GroupResponse");
}

/**
 * Create a new group.
 *
 * `name` must not collide with an existing group. `group_admins` lists user IDs
 * to make group admins; the current user is added as an admin automatically.
 */
export async function postGroup(
  client: SkyPortalClient,
  payload: GroupPost,
): Promise<GroupPostResponse> {
  const data = await client.request("POST", "/api/groups", { body: payload });
  return parse(GroupPostResponseSchema, data, "GroupPostResponse");
}

/**
 * Update an existing group.
 *
 * Only the provided fields are sent; omitted fields are left unchanged. `name`
 * is required by the server even when unchanged.
 */
export async function updateGroup(
  client: SkyPortalClient,
  groupId: number,
  name: string,
  options: {
    nickname?: string;
    description?: string;
    private?: boolean;
    autoAcceptRequests?: boolean;
  } = {},
): Promise<void> {
  await client.request("PUT", `/api/groups/${groupId}`, {
    body: {
      name,
      ...(options.nickname !== undefined && { nickname: options.nickname }),
      ...(options.description !== undefined && {
        description: options.description,
      }),
      ...(options.private !== undefined && { private: options.private }),
      ...(options.autoAcceptRequests !== undefined && {
        auto_accept_requests: options.autoAcceptRequests,
      }),
    },
  });
}

/** Delete a group. */
export async function deleteGroup(
  client: SkyPortalClient,
  groupId: number,
): Promise<void> {
  await client.request("DELETE", `/api/groups/${groupId}`);
}

/**
 * Grant a group access to an alert stream.
 *
 * Every member of the group must already have access to the stream.
 */
export async function postGroupStream(
  client: SkyPortalClient,
  groupId: number,
  streamId: number,
): Promise<GroupStreamPostResponse> {
  const data = await client.request("POST", `/api/groups/${groupId}/streams`, {
    body: { stream_id: streamId },
  });
  return parse(GroupStreamPostResponseSchema, data, "GroupStreamPostResponse");
}

/**
 * Remove an alert stream from a group.
 *
 * Fails if one of the group's filters still operates on the stream.
 */
export async function deleteGroupStream(
  client: SkyPortalClient,
  groupId: number,
  streamId: number,
): Promise<void> {
  await client.request("DELETE", `/api/groups/${groupId}/streams/${streamId}`);
}

/**
 * Add a user to a group.
 *
 * The user must already have access to every stream of the group.
 */
export async function postGroupUser(
  client: SkyPortalClient,
  groupId: number,
  userId: number,
  options: {
    admin?: boolean;
    canSave?: boolean;
    canSharePhotometry?: boolean;
  } = {},
): Promise<GroupUserPostResponse> {
  const data = await client.request("POST", `/api/groups/${groupId}/users`, {
    body: {
      userID: userId,
      admin: options.admin ?? false,
      canSave: options.canSave ?? true,
      canSharePhotometry: options.canSharePhotometry ?? false,
    },
  });
  return parse(GroupUserPostResponseSchema, data, "GroupUserPostResponse");
}

/**
 * Update a group member's admin or save-access status.
 *
 * At least one flag must be provided; omitted flags are left unchanged.
 */
export async function updateGroupUser(
  client: SkyPortalClient,
  groupId: number,
  userId: number,
  options: {
    admin?: boolean;
    canSave?: boolean;
    canSharePhotometry?: boolean;
  } = {},
): Promise<void> {
  await client.request("PATCH", `/api/groups/${groupId}/users`, {
    body: {
      userID: userId,
      ...(options.admin !== undefined && { admin: options.admin }),
      ...(options.canSave !== undefined && { canSave: options.canSave }),
      ...(options.canSharePhotometry !== undefined && {
        canSharePhotometry: options.canSharePhotometry,
      }),
    },
  });
}

/** Remove a user from a group. */
export async function deleteGroupUser(
  client: SkyPortalClient,
  groupId: number,
  userId: number,
): Promise<void> {
  await client.request("DELETE", `/api/groups/${groupId}/users/${userId}`);
}

/**
 * Add all members of other groups to the specified group.
 *
 * Users already in the target group are skipped.
 */
export async function postGroupUsersFromGroups(
  client: SkyPortalClient,
  groupId: number,
  fromGroupIds: number[],
): Promise<void> {
  await client.request("POST", `/api/groups/${groupId}/usersFromGroups`, {
    body: { fromGroupIDs: fromGroupIds },
  });
}
