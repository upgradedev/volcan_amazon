"""Unit tests for Adaptive Switch & Motor Impairment Accessibility."""
from src.application.accessibility_use_case import AccessibilityOrchestratorUseCase
from src.domain.adaptive_switch import (
    SwitchAction,
    SwitchInputType,
    SwitchNavigationState,
    SwitchSignal,
)


def test_sip_and_puff_mapping():
    # Strong positive puff -> Confirm
    puff = SwitchSignal(
        input_type=SwitchInputType.SIP_AND_PUFF,
        signal_strength=0.8,
        duration_ms=200,
        is_long_press=False,
    )
    assert puff.map_to_action() == SwitchAction.CONFIRM_LEASE

    # Low sip -> Reject
    sip = SwitchSignal(
        input_type=SwitchInputType.SIP_AND_PUFF,
        signal_strength=0.2,
        duration_ms=200,
        is_long_press=False,
    )
    assert sip.map_to_action() == SwitchAction.REJECT_LEASE


def test_single_button_long_press_emergency_stop():
    long_press = SwitchSignal(
        input_type=SwitchInputType.SINGLE_BUTTON,
        signal_strength=1.0,
        duration_ms=1200,
        is_long_press=True,
    )
    assert long_press.map_to_action() == SwitchAction.TRIGGER_EMERGENCY_STOP


def test_switch_navigation_state_advance():
    state = SwitchNavigationState(
        current_focus_index=0,
        total_sections=3,
        is_scanning_active=True,
    )
    next_state = state.advance_scan()
    assert next_state.current_focus_index == 1
    assert next_state.is_scanning_active is True

    wrap_state = next_state.advance_scan().advance_scan()
    assert wrap_state.current_focus_index == 0


def test_accessibility_orchestrator_use_case():
    use_case = AccessibilityOrchestratorUseCase()
    res = use_case.process_switch_signal("SIP_AND_PUFF", signal_strength=0.9)
    assert res["resolved_action"] == "CONFIRM_LEASE"
    assert "Switch pulse resolved" in res["description"]
