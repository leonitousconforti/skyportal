import { useEffect, useState } from "react";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { showNotification } from "baselayer/components/Notifications";
import { useAppDispatch } from "../../../types/hooks";
import type { AIConnectionTest } from "../../../ducks/aiConnection";
import {
  useDeleteAIConnectionMutation,
  useGetAIConnectionQuery,
  useTestAIConnectionMutation,
  useUpdateAIConnectionMutation,
} from "../../../ducks/aiConnection";
import { useGetConfigQuery } from "../../../ducks/config";
import Button from "../../Button";
import CustomizeOpenAIParameters from "./CustomizeOpenAIParameters";

const PROVIDERS = [
  { value: "openai_compatible", label: "OpenAI-compatible" },
  { value: "anthropic", label: "Anthropic" },
];

const TEST_SEVERITY = {
  works: "success",
  no_tool_calls: "warning",
  failed: "error",
} as const;

const AIConnectionPreferences = () => {
  const dispatch = useAppDispatch();
  const { data: connection, isLoading } = useGetAIConnectionQuery();
  const [updateConnection, { isLoading: isSaving }] =
    useUpdateAIConnectionMutation();
  const [deleteConnection, { isLoading: isRemoving }] =
    useDeleteAIConnectionMutation();
  const [testConnection, { isLoading: isTesting }] =
    useTestAIConnectionMutation();
  const assistantUserKeys =
    useGetConfigQuery().data?.["assistantUserKeys"] === true;

  const [provider, setProvider] = useState("openai_compatible");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiKeyError, setApiKeyError] = useState(false);
  const [baseUrlError, setBaseUrlError] = useState(false);
  const [modelError, setModelError] = useState(false);
  const [testResult, setTestResult] = useState<AIConnectionTest | null>(null);

  // The saved key is never sent back, so its field always starts blank.
  useEffect(() => {
    setProvider(connection?.provider ?? "openai_compatible");
    setBaseUrl(connection?.base_url ?? "");
    setModel(connection?.model ?? "");
    setApiKey("");
    setApiKeyError(false);
    setBaseUrlError(false);
    setModelError(false);
    setTestResult(null);
  }, [connection]);

  if (isLoading) {
    return null;
  }

  const trimmedBaseUrl = baseUrl.trim();
  const isAnthropic = provider === "anthropic";
  // A saved key is only sent where it was saved for, so a new address needs it.
  const apiKeyRequired =
    !connection?.api_key_set ||
    provider !== connection.provider ||
    (trimmedBaseUrl || null) !== connection.base_url;

  // The test runs on the saved connection, so edits have to be saved first.
  const edited =
    !connection ||
    provider !== connection.provider ||
    (trimmedBaseUrl || null) !== connection.base_url ||
    (model.trim() || null) !== connection.model ||
    apiKey.trim() !== "";

  let apiKeyPlaceholder = "";
  if (connection?.api_key_set) {
    apiKeyPlaceholder = connection.api_key_last4
      ? `Saved key ending in ${connection.api_key_last4}`
      : "A key is saved";
  }

  let apiKeyHelperText = "";
  if (apiKeyError) {
    apiKeyHelperText = "An API key is required";
  } else if (connection?.api_key_set && apiKeyRequired) {
    apiKeyHelperText =
      "Enter the key again: a saved key is only sent to the provider and base URL it was saved for";
  } else if (connection?.api_key_set) {
    apiKeyHelperText = "Leave blank to keep the saved key";
  }

  let baseUrlHelperText =
    "Leave blank for OpenAI. Any https service speaking the OpenAI chat-completions protocol works, e.g. OpenRouter, Gemini or an institutional gateway; your key is only ever sent here.";
  if (baseUrlError) {
    baseUrlHelperText = "Must be an https:// URL";
  } else if (isAnthropic) {
    baseUrlHelperText =
      "Leave blank for api.anthropic.com; your key is only ever sent here.";
  }

  const modelMissing = modelError && isAnthropic;
  let modelHelperText = assistantUserKeys
    ? "The assistant needs a model here. Left blank, summaries use the one in your summary settings or this instance's default"
    : "Leave blank for the model in your summary settings or this instance's default";
  if (modelMissing) {
    modelHelperText = "A model is required for Anthropic";
  } else if (isAnthropic) {
    modelHelperText = assistantUserKeys
      ? "The Claude model to use, for summaries and the assistant"
      : "The Claude model to use for summaries";
  }

  const onSave = async () => {
    const badUrl =
      trimmedBaseUrl !== "" && !trimmedBaseUrl.startsWith("https://");
    const missingKey = apiKeyRequired && !apiKey.trim();
    // The summary settings and this instance's default name OpenAI models.
    const missingModel = isAnthropic && !model.trim();
    setBaseUrlError(badUrl);
    setApiKeyError(missingKey);
    setModelError(missingModel);
    if (badUrl || missingKey || missingModel) {
      return;
    }
    try {
      await updateConnection({
        provider,
        base_url: trimmedBaseUrl || null,
        model: model.trim() || null,
        api_key: apiKey.trim() || null,
      }).unwrap();
      setApiKey("");
      dispatch(showNotification("AI provider saved"));
    } catch {
      // error notification handled by the baseQuery
    }
  };

  const onTest = async () => {
    setTestResult(null);
    try {
      setTestResult(await testConnection().unwrap());
    } catch {
      // error notification handled by the baseQuery
    }
  };

  const onRemove = async () => {
    try {
      await deleteConnection().unwrap();
      dispatch(showNotification("AI provider removed"));
    } catch {
      // error notification handled by the baseQuery
    }
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {assistantUserKeys && (
        <Typography variant="body2" color="textSecondary">
          The assistant answers your chat questions with this connection too, so
          your questions, and what its tools read for you, go to this provider.
        </Typography>
      )}
      <TextField
        select
        name="provider"
        label="Provider"
        fullWidth
        value={provider}
        onChange={(event) => setProvider(event.target.value)}
        data-testid="AIConnection_provider"
      >
        {PROVIDERS.map(({ value, label }) => (
          <MenuItem key={value} value={value}>
            {label}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        name="base_url"
        label="Base URL (optional)"
        fullWidth
        placeholder={
          isAnthropic
            ? "https://api.anthropic.com"
            : "https://api.openai.com/v1"
        }
        value={baseUrl}
        onChange={(event) => setBaseUrl(event.target.value)}
        data-testid="AIConnection_base_url"
        helperText={baseUrlHelperText}
        error={baseUrlError}
      />
      <TextField
        name="model"
        label={isAnthropic ? "Model" : "Model (optional)"}
        fullWidth
        required={isAnthropic}
        placeholder={isAnthropic ? "claude-opus-5-5" : ""}
        value={model}
        onChange={(event) => setModel(event.target.value)}
        data-testid="AIConnection_model"
        helperText={modelHelperText}
        error={modelMissing}
      />
      <TextField
        name="api_key"
        type="password"
        label="API key"
        fullWidth
        required={apiKeyRequired}
        autoComplete="new-password"
        placeholder={apiKeyPlaceholder}
        value={apiKey}
        onChange={(event) => setApiKey(event.target.value)}
        data-testid="AIConnection_api_key"
        helperText={apiKeyHelperText}
        error={apiKeyError}
      />
      <Box sx={{ display: "flex", gap: 1 }}>
        <Button
          primary
          onClick={onSave}
          disabled={isSaving}
          data-testid="AIConnection_save"
        >
          Save
        </Button>
        {connection && assistantUserKeys && (
          <Button
            async
            loading={isTesting}
            onClick={onTest}
            disabled={edited}
            data-testid="AIConnection_test"
          >
            Test connection
          </Button>
        )}
        {connection && (
          <Button
            secondary
            onClick={onRemove}
            disabled={isRemoving}
            data-testid="AIConnection_remove"
          >
            Remove
          </Button>
        )}
      </Box>
      {testResult && (
        <Alert
          severity={TEST_SEVERITY[testResult.outcome]}
          data-testid="AIConnection_test_result"
        >
          {testResult.message}
        </Alert>
      )}
      {connection && <CustomizeOpenAIParameters />}
    </Box>
  );
};

export default AIConnectionPreferences;
