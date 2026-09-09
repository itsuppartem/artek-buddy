from __future__ import annotations

from artek_buddy.runtime import scripted, scripted_scenarios


def test_e2e_prompts_live_on_the_scenario_module() -> None:
    fail = scripted_scenarios.steps_for_prompt("please e2e-fail now")
    assert fail[-1].status == "failed"
    assert fail[-1].error == scripted_scenarios.E2E_FAIL_ERROR
    assert scripted.steps_for_prompt is scripted_scenarios.steps_for_prompt
    assert scripted.E2E_FAIL_ERROR is scripted_scenarios.E2E_FAIL_ERROR
    assert scripted.ScriptedRuntime is not getattr(scripted_scenarios, "ScriptedRuntime", None)
    assert not hasattr(scripted_scenarios, "ScriptedRuntime")
