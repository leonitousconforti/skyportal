import { useState } from "react";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import { skipToken } from "@reduxjs/toolkit/query";

import SurveyEfficiencyForm from "./SurveyEfficiencyForm";
import SurveyEfficiencyObservationPlanLists from "./SurveyEfficiencyObservationPlanLists";

import Button from "../Button";
import { useGetObservationPlanSurveyEfficiencyQuery } from "../../ducks/survey_efficiency_observation_plans";

interface AddSurveyEfficiencyObservationPlanPageProps {
  gcnevent: {
    dateobs?: string;
    localizations?: { id?: number; localization_name?: string }[];
    id?: number;
    [key: string]: any;
  };
  observationplanRequest: {
    id?: number;
    status?: string;
    [key: string]: any;
  };
}

const AddSurveyEfficiencyObservationPlanPage = ({
  gcnevent,
  observationplanRequest,
}: AddSurveyEfficiencyObservationPlanPageProps) => {
  const [dialogOpen, setDialogOpen] = useState(false);

  const planID =
    observationplanRequest?.status === "complete"
      ? observationplanRequest.id
      : undefined;
  const { data: surveyEfficiencyAnalysisList } =
    useGetObservationPlanSurveyEfficiencyQuery(planID ?? skipToken);

  const openDialog = () => {
    setDialogOpen(true);
  };

  const closeDialog = () => {
    setDialogOpen(false);
  };

  return (
    <>
      <Button
        secondary
        size="small"
        onClick={openDialog}
        data-testid={`addSimSurveyButton_${gcnevent.id}`}
      >
        SimSurvey Analysis
      </Button>
      <Dialog open={dialogOpen} onClose={closeDialog}>
        <DialogTitle>SimSurvey Analysis</DialogTitle>
        <DialogContent>
          <div>
            <SurveyEfficiencyForm
              gcnevent={gcnevent}
              observationplanRequest={observationplanRequest}
            />
            {!!surveyEfficiencyAnalysisList?.length && (
              <SurveyEfficiencyObservationPlanLists
                survey_efficiency_analyses={surveyEfficiencyAnalysisList}
              />
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default AddSurveyEfficiencyObservationPlanPage;
