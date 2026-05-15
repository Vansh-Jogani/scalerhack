"""T3.5 — DroneInterface is a real ABC and DroneModel satisfies it."""

import pytest

from sim.drone_interface import DroneInterface, Telemetry
from sim.drone_model import DroneModel


class MockSITLDrone(DroneInterface):
    """Stub V2 SITL drone — empty bodies must satisfy the interface."""

    def tick(self, dt: float) -> None:
        pass

    def set_target(self, lat: float, lon: float, alt: float) -> None:
        pass

    def return_to_launch(self) -> None:
        pass

    def get_telemetry(self) -> Telemetry:
        return Telemetry("mock", 0.0, 0.0, 0.0, 0.0, 0.0, "IDLE", 100.0)

    def get_state(self) -> str:
        return "IDLE"


def test_drone_interface_is_abstract():
    with pytest.raises(TypeError):
        DroneInterface()  # type: ignore[abstract]


def test_drone_model_implements_interface():
    drone = DroneModel("d1", "fixed_wing", 0.0, 0.0)
    assert isinstance(drone, DroneInterface)


def test_mock_sitl_drone_satisfies_interface():
    drone = MockSITLDrone()
    assert isinstance(drone, DroneInterface)
    # Every abstract method is callable without raising
    drone.tick(0.1)
    drone.set_target(0.0, 0.0, 100.0)
    drone.return_to_launch()
    t = drone.get_telemetry()
    assert isinstance(t, Telemetry)
    assert drone.get_state() == "IDLE"


def test_no_agent_imports_drone_model_directly():
    """Agents must not import DroneModel — only DroneInterface-typed handles."""
    import ast
    from pathlib import Path

    agents_dir = Path(__file__).parent.parent / "agents"
    violations = []
    for py_file in agents_dir.rglob("*.py"):
        src = py_file.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.ImportFrom):
                    if node.module and "drone_model" in node.module:
                        violations.append(str(py_file))
                else:
                    for alias in node.names:
                        if "drone_model" in alias.name:
                            violations.append(str(py_file))
    assert violations == [], f"Agent files import DroneModel directly: {violations}"
