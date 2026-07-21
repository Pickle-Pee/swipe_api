import pytest

from main_app.controllers.user_controller import _distance_km


def test_distance_is_zero_for_the_same_point():
    assert _distance_km(37.619423, 55.752244, 37.619423, 55.752244) == 0


def test_distance_is_calculated_in_kilometres_without_postgis():
    distance = _distance_km(37.619423, 55.752244, 37.631423, 55.764244)

    assert distance == pytest.approx(1.53, abs=0.02)
