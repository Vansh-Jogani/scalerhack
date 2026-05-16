from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Telemetry:
    drone_id: str
    lat: float
    lon: float
    alt: float
    heading: float
    speed: float
    state: str
    battery_pct: float
<<<<<<< HEAD
    drone_type: str = "fixed_wing"
=======
    drone_type: str = field(default="unknown")
>>>>>>> 24c6382f974245ec571eddb1af70efedb54b5a47


class DroneInterface(ABC):
    @abstractmethod
    def tick(self, dt: float) -> None:
        ...

    @abstractmethod
    def set_target(self, lat: float, lon: float, alt: float) -> None:
        ...

    @abstractmethod
    def return_to_launch(self) -> None:
        ...

    @abstractmethod
    def get_telemetry(self) -> Telemetry:
        ...

    @abstractmethod
    def get_state(self) -> str:
        ...
