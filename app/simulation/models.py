"""All Dataclass models for the program"""

from dataclasses import dataclass


@dataclass
class SimulationStep:
    """An instance of one step of the simulation"""

    river_snapshot: RiverNetwork
    """A snapshot of the river network at a time step"""

    year: int
    """The year of the simulation"""

    @property
    def cells_flooded(self) -> list[Cell]:
        """A list of all cell currently flooded"""

        flooded_cells: list[Cell] = []

        for edge in self.river_snapshot.get_edges():
            for cell in edge.cells:
                if cell.flooded_state:
                    flooded_cells.append(cell)

        return flooded_cells

    @property
    def dams_broken(self) -> list[Dam]:
        """A list of all dams broken in this step"""

        broken_dams: list[Dam] = []

        for edge in self.river_snapshot.get_edges():
            for cell in edge.cells:
                if cell.dam.is_broken:
                    if cell.dam.broken_year == self.year:
                        broken_dams.append(cell)

        return broken_dams

    @property
    def dams_created(self) -> list[Dam]:
        """A list of all dams created in this step"""

        created_dams: list[Dam] = []

        for edge in self.river_snapshot.get_edges():
            for cell in edge.cells:
                if not cell.dam.is_broken:
                    if cell.dam.create_year == self.year:
                        created_dams.append(cell)

        return created_dams


@dataclass
class SimParam:
    """The parameters of the Simulation"""

    dam_break_probability: float
    """The probability a dam breaks"""

    dam_creation_probability: float
    """The probability a dam is created"""

    flood_probability: float
    """The probability a catastrophic flood event occurs when a dam breaks"""

    flood_break_probability: float
    """The probability a flood will break a dam"""

    stabilization_time: int
    """The time in years/steps it takes for a cell to return to a unfounded state"""

    years: int
    """The number of years/steps the simulation will run"""

    random_seed: int
    """The random seed to use"""

    def __post_init__(self):
        """Check if the parameters are valid"""
        
        probs = [self.dam_creation_probability,
                 self.dam_break_probability,
                 self.flood_probability,
                 self.flood_break_probability,
                 ]
        if self.years <= 0:
            raise ValueError("Years must be positive")
        if self.stabilization_time <= 0:
            raise ValueError("Stabilization time must be positive")
        if self.random_seed is None:
            raise ValueError("Random seed must be provided")
        for prob in probs:
            if not (0 <= prob <= 1):
                raise ValueError("Probability must be between 0 and 1")


@dataclass
class RiverNode:


@dataclass
class RiverEdge:
    __init__

@dataclass
class Cell:

@dataclass
class Dam: