/**
 * Survey efficiency analyses for observation plans.
 *
 * RTK Query conversion of the old `FETCH_SURVEY_EFFICIENCY_OBSERVATION_PLANS`
 * duck. The list queries (all analyses, and one plan's) are injected into the
 * central `skyportalApi` and provide the `SurveyEfficiencyObservationPlan` tag;
 * submit and delete are mutations that invalidate it so any active list
 * refetches.
 *
 * Submit issues a `simsurvey` run (the backend kicks off the analysis); the old
 * duck used `API.GET` for it, so the mutation keeps the `GET` method with the
 * form data as query params.
 */
import { skyportalApi } from "../api/skyportalApi";
import type { RouteData } from "../types/routeSchemaMap";

export const surveyEfficiencyObservationPlansApi = skyportalApi.injectEndpoints(
  {
    endpoints: (build) => ({
      getSurveyEfficiencyObservationPlans: build.query<
        RouteData<"GET /api/survey_efficiency/observation_plan">,
        void
      >({
        query: () => "api/survey_efficiency/observation_plan",
        providesTags: ["SurveyEfficiencyObservationPlan"],
      }),
      getObservationPlanSurveyEfficiency: build.query<
        RouteData<"GET /api/observation_plan/{observation_plan_request_id}/survey_efficiency">,
        number | string
      >({
        query: (id) => `api/observation_plan/${id}/survey_efficiency`,
        providesTags: ["SurveyEfficiencyObservationPlan"],
      }),
      submitSurveyEfficiencyObservationPlan: build.mutation<
        unknown,
        { id: number | string; data?: Record<string, any> | undefined }
      >({
        query: ({ id, data = {} }) => ({
          url: `api/observation_plan/${id}/simsurvey`,
          method: "GET",
          params: data,
        }),
        invalidatesTags: ["SurveyEfficiencyObservationPlan"],
      }),
      deleteSurveyEfficiencyObservationPlan: build.mutation<
        unknown,
        number | string
      >({
        query: (id) => ({
          url: `api/observation_plan/${id}/simsurvey`,
          method: "DELETE",
        }),
        invalidatesTags: ["SurveyEfficiencyObservationPlan"],
      }),
    }),
  },
);

export const {
  useGetSurveyEfficiencyObservationPlansQuery,
  useGetObservationPlanSurveyEfficiencyQuery,
  useSubmitSurveyEfficiencyObservationPlanMutation,
  useDeleteSurveyEfficiencyObservationPlanMutation,
} = surveyEfficiencyObservationPlansApi;
