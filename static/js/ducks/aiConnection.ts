/**
 * The user's own AI provider connection. The key is write-only: a read says
 * whether one is saved and its last four characters, never the key itself.
 */
import { skyportalApi } from "../api/skyportalApi";

export interface AIConnection {
  provider: string;
  base_url: string | null;
  model: string | null;
  api_key_set: boolean;
  api_key_last4: string | null;
}

export interface AIConnectionPut {
  provider: string;
  base_url: string | null;
  model: string | null;
  /** Blank keeps the saved key, unless the provider or base URL changes. */
  api_key: string | null;
}

/** What a test of the saved connection found. */
export interface AIConnectionTest {
  outcome: "works" | "no_tool_calls" | "failed";
  message: string;
}

export const aiConnectionApi = skyportalApi.injectEndpoints({
  endpoints: (build) => ({
    getAIConnection: build.query<AIConnection | null, void>({
      query: () => "api/internal/ai_connection",
      providesTags: ["AIConnection"],
    }),
    updateAIConnection: build.mutation<void, AIConnectionPut>({
      query: (body) => ({
        url: "api/internal/ai_connection",
        method: "PUT",
        body,
      }),
      invalidatesTags: ["AIConnection"],
    }),
    deleteAIConnection: build.mutation<void, void>({
      query: () => ({ url: "api/internal/ai_connection", method: "DELETE" }),
      invalidatesTags: ["AIConnection"],
    }),
    testAIConnection: build.mutation<AIConnectionTest, void>({
      query: () => ({ url: "api/internal/ai_connection/test", method: "POST" }),
    }),
  }),
});

export const {
  useGetAIConnectionQuery,
  useUpdateAIConnectionMutation,
  useDeleteAIConnectionMutation,
  useTestAIConnectionMutation,
} = aiConnectionApi;
