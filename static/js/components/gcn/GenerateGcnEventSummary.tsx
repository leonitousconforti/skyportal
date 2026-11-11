import { useState } from "react";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import SmartToyTwoToneIcon from "@mui/icons-material/SmartToyTwoTone";
import Tooltip from "@mui/material/Tooltip";

import { showNotification } from "baselayer/components/Notifications";
import { useAppDispatch } from "../../types/hooks";
import { useGetConfigQuery } from "../../ducks/config";
import { useGetAIConnectionQuery } from "../../ducks/aiConnection";
import { useSummarizeGcnEventMutation } from "../../ducks/gcnEvent";

interface GenerateGcnEventSummaryProps {
  dateobs: string;
}

const GenerateGcnEventSummary = ({ dateobs }: GenerateGcnEventSummaryProps) => {
  const dispatch = useAppDispatch();
  const [summarizeGcnEvent] = useSummarizeGcnEventMutation();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { data: config } = useGetConfigQuery() as { data: any };
  const { data: aiConnection } = useGetAIConnectionQuery();

  // Nothing to click unless a model is reachable.
  if (!config?.summary_apikey_set && !aiConnection) {
    return null;
  }

  const onClick = async () => {
    setIsSubmitting(true);
    try {
      await summarizeGcnEvent(dateobs).unwrap();
      dispatch(showNotification("Event summary generated."));
    } catch {
      // error notification handled by the baseQuery
    }
    setIsSubmitting(false);
  };

  return isSubmitting ? (
    <CircularProgress size="1rem" />
  ) : (
    <Tooltip title="Summarize this event from its extractions">
      <IconButton
        size="small"
        onClick={onClick}
        data-testid="generateGcnSummaryButton"
      >
        <SmartToyTwoToneIcon fontSize="small" />
      </IconButton>
    </Tooltip>
  );
};

export default GenerateGcnEventSummary;
