"""All Dataclass models for the program"""
from __future__ import annotations
from dataclasses import dataclass,field
from itertools import count
from typing import ClassVar


class RiverNetwork:
    """A directed graph representing a river network."""

    nodes: list[RiverNode]
    edges: list[RiverEdge]

    def add_node(self) -> None:
        """Add a new node to the graph."""
        self.nodes.append(RiverNode())

    def add_edge(self, down_stream_node, up_stream_node) -> None:
        """Add an edge to the graph and connect it nodes."""
        self.edges.append(RiverEdge(down_stream_node, up_stream_node))


@dataclass
class RiverNode:
    """A node representing an intersection of two segments of river"""

    _node_counter: ClassVar[count] = count(1)

    down_stream_edge: RiverEdge | None = None
    """The edge that is downstream of this node"""

    up_stream_edge: list[RiverEdge] | None = None
    """The edges that are upstream of this node"""

    id: int = field(default_factory=lambda: next(RiverNode._node_counter))
    """The id of the Node"""


@dataclass
class RiverEdge:
    """An edge representing a segment of river that does not join another segment of river"""

    _edge_counter: ClassVar[count] = count(1)

    down_stream_node: RiverNode
    """The node downstream of the edge"""

    up_stream_node: RiverNode
    """The node upstream of the edge"""

    cells: dict[int, Cell] | None = None
    """The cells that are on the edge held with their position"""

    id: int = field(default_factory=lambda: next(RiverEdge._edge_counter))
    """The id of the Edge"""

    length: int = 100
    """The length of the edge, must be whole number"""

    def create_cells(self) -> None:
        """Create all cells needed for the edge."""

        num_cells = int(self.length/10) #magic 10 might be user defined in future
        cells = {}

        for i in range(num_cells):
            cell = Cell(self, i+1)
            cells[i+1] = cell

        self.cells = cells

    def __post_init__(self):
        self.create_cells()


@dataclass
class Cell:
    """A distinct area cell of the river edge"""

    _cell_counter: ClassVar[count] = count(1)

    edge: RiverEdge
    """The edge that the cell exists on"""

    position: int
    """The position of the cell as its position relative other cells to the upstream of a edge"""

    id: int = field(default_factory=lambda: next(Cell._cell_counter))
    """The id of the cell"""

    dam: Dam | None = None
    """A dam that may exist in a cell"""

    flooded: bool | None = False
    """If a cell is flooded"""

    flooded_time: int | None = None
    """How long a cell has been flooded"""


@dataclass
class Dam:
    """A dam"""

    _dam_counter: ClassVar[count] = count(1)

    cell: Cell
    """Which cell the dam is in"""

    created_year: int
    """The year the dam was created"""

    id: int = field(default_factory=lambda: next(Dam._dam_counter))
    """Unique id for the dam"""

    meadow: bool = False
    """Whether the dam is a beaver meadow"""

    broken_year: int | None = None
    """The year the dam was broken"""

    @property
    def is_broken(self) -> bool:
        return self.broken_year is not None


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

        for edge in self.river_snapshot.edges:
            for cell in edge.cells:
                if cell.flooded_state:
                    flooded_cells.append(cell)

        return flooded_cells

    @property
    def dams_broken(self) -> list[Dam]:
        """A list of all dams broken in this step"""

        broken_dams: list[Dam] = []

        for edge in self.river_snapshot.edges:
            for cell in edge.cells:
                if cell.dam.is_broken:
                    if cell.dam.broken_year == self.year:
                        broken_dams.append(cell)

        return broken_dams

    @property
    def dams_created(self) -> list[Dam]:
        """A list of all dams created in this step"""

        created_dams: list[Dam] = []

        for edge in self.river_snapshot.edges:
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
        for prob in probs:
            if not (0 <= prob <= 1):
                raise ValueError("Probability must be between 0 and 1")
