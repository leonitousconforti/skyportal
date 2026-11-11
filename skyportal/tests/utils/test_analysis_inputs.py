"""What an analysis sends its service, against what it stores."""

from skyportal.handlers.api.analysis import _analysis_inputs


def test_the_ai_key_reaches_the_service_but_is_not_stored():
    summary_parameters = {"model": "gpt-4o-mini", "temperature": 0.1}
    params = {"openai_api_key": "sk-secret", "summary_parameters": summary_parameters}

    inputs, _ = _analysis_inputs(params)

    assert inputs["analysis_parameters"]["openai_api_key"] == "sk-secret"
    # params is what the analysis row keeps.
    assert params == {"summary_parameters": summary_parameters}


def test_parameters_without_a_key_are_stored_unchanged():
    params = {"correct_extinction": True}

    inputs, correct_extinction = _analysis_inputs(params)

    assert inputs["analysis_parameters"] == {"correct_extinction": True}
    assert params == {"correct_extinction": True}
    assert correct_extinction is True
