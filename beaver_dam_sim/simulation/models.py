"""All Dataclass models for the program"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from itertools import count
from typing import ClassVar


class RiverNetwork:
    """A directed graph representing a river network."""

    nodes: list[RiverNode]
    edges: list[RiverEdge]

    @property
    def terminal_node(self) -> RiverNode:
        """The terminal node of the graph."""
        return next((node for node in self.nodes if node.is_terminal))

    def __init__(self):
        self.nodes = []
        self.edges = []

    def add_node(self) -> None:
        """Add a new node to the graph."""
        self.nodes.append(RiverNode())

    def add_edge(self, down_stream_node, up_stream_node) -> None:
        """Add an edge to the graph and connect it nodes."""
        new_edge = RiverEdge(down_stream_node, up_stream_node)

        if down_stream_node.up_stream_edge is None:
            down_stream_node.up_stream_edge = []

        down_stream_node.up_stream_edge.append(new_edge)
        up_stream_node.down_stream_edge = new_edge

        self.edges.append(new_edge)

    def shreve_order(self) -> None:
        """Assign Shreve order numbering to each edge"""

        ordered_nodes: list[RiverNode] = []
        queue = deque([self.terminal_node])

        #add starting order at 1 for outer edges
        for edge in (e for e in self.edges if e.is_outer_edge):
            edge.stream_order = 1

        #collect list of each node in terminal-up order from root node (sort)
        while queue:
            node = queue.popleft()

            #this should happen, but if it does, don't.
            if node.up_stream_edge is None:
                continue

            ordered_nodes.append(node)

            #only add nodes that don't have terminal outer edges that already have order value 1
            for edge in node.up_stream_edge:
                if not edge.is_outer_edge:
                    queue.append(edge.up_stream_node)

        #iterate list collecting both upstream edges and adding order to downstream edge
        while ordered_nodes:
            node = ordered_nodes.pop()

            #should only happen for terminal node
            if node.down_stream_edge is None:
                continue

            value = 0

            for edge in node.up_stream_edge:
                value += edge.stream_order

            node.down_stream_edge.stream_order = value

        #profit after 30 **** hours

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

    @property
    def is_terminal(self) -> bool:
        """Return True if the node is terminal"""
        return self.down_stream_edge is None

@dataclass
class RiverEdge:
    """An edge representing a segment of river that does not join another segment of river"""

    _edge_counter: ClassVar[count] = count(1)

    down_stream_node: RiverNode
    """The node downstream of the edge"""

    up_stream_node: RiverNode
    """The node upstream of the edge"""

    cells: dict[int, Cell] = field(default_factory=dict)
    """The cells that are on the edge held with their position"""

    id: int = field(default_factory=lambda: next(RiverEdge._edge_counter))
    """The id of the Edge"""

    length: int = 100
    """The length of the edge, must be whole number"""

    stream_order: int = None
    """The order of the edge based on Shreve order"""

    @property
    def is_outer_edge(self) -> bool:
        """The edge is the last edge on its line"""
        return self.up_stream_node.up_stream_edge is None

    def create_cells(self) -> None:
        """Create all cells needed for the edge."""

        num_cells = int(self.length / 10)  # magic 10 might be user defined in future
        cells = {}

        for i in range(num_cells):
            cell = Cell(self, i + 1)
            cells[i + 1] = cell

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
    """The position of the cell as its position relative other cells to the upstream of a edge starting at 1"""

    id: int = field(default_factory=lambda: next(Cell._cell_counter))
    """The id of the cell"""

    dam: Dam | None = None
    """A dam that may exist in a cell"""

    flooded_step: int | None = None
    """The step the dam was flooded"""

    @property
    def flooded(self) -> bool:
        """If the cell is flooded"""

        return self.flooded_step is not None

    def flooded_time(self, step) -> int:
        """How long the cell has been flooded"""

        assert self.flooded_step is not None
        return step - self.flooded_step

    def create_dam(self, step) -> None:
        """Create the dam for this cell"""
        self.dam = Dam(self, step)

    def flood(self, step) -> None:
        """Flood the cell"""
        self.flooded_step = step

    def clear_flood(self) -> None:
        """Clear the cell flooding"""
        self.flooded_step = None


@dataclass
class Dam:
    """A dam"""

    _dam_counter: ClassVar[count] = count(1)

    cell: Cell
    """Which cell the dam is in"""

    created_step: int
    """The step the dam was created"""

    id: int = field(default_factory=lambda: next(Dam._dam_counter))
    """Unique id for the dam"""

    meadow: bool = False
    """Whether the dam is a beaver meadow"""

    broken_step: int | None = None
    """The step the dam was broken"""

    @property
    def broken(self) -> bool:
        return self.broken_step is not None

    def break_dam(self, step: int) -> None:
        """Break the dam"""
        self.broken_step = step

    def make_meadow(self) -> None:
        """Make the dam a meadow"""
        assert self.broken
        self.meadow = True


@dataclass
class SimulationStep:
    """An instance of one step of the simulation"""

    river_snapshot: RiverNetwork
    """A snapshot of the river network at a time step"""

    step: int
    """The step of the simulation"""

    @property
    def cells_flooded(self) -> list[Cell]:
        """A list of all cell currently flooded"""

        flooded_cells: list[Cell] = []

        for edge in self.river_snapshot.edges:
            for cell in edge.cells.values():
                if cell.flooded:
                    flooded_cells.append(cell)

        return flooded_cells

    @property
    def dams_broken(self) -> list[Dam]:
        """A list of all dams broken in this step"""

        broken_dams: list[Dam] = []

        for edge in self.river_snapshot.edges:
            for cell in edge.cells.values():
                if cell.dam and cell.dam.broken:
                    if cell.dam.broken_step == self.step:
                        broken_dams.append(cell.dam)

        return broken_dams

    @property
    def dams_created(self) -> list[Dam]:
        """A list of all dams created in this step"""

        created_dams: list[Dam] = []

        for edge in self.river_snapshot.edges:
            for cell in edge.cells.values():
                if cell.dam and not cell.dam.broken:
                    if cell.dam.created_step == self.step:
                        created_dams.append(cell.dam)

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
    """The time in years/steps it takes for a cell to return to a unflooded state"""

    steps: int
    """The number of years/steps the simulation will run"""

    random_seed: int
    """The random seed to use"""

    meadow_probability: float = 0
    """The probability a meadow will occur when a dam breaks"""

    def __post_init__(self):
        """Check if the parameters are valid"""

        probs = [self.dam_creation_probability,
                 self.dam_break_probability,
                 self.flood_probability,
                 self.flood_break_probability,
                 self.meadow_probability,
                 ]
        if self.steps <= 0:
            raise ValueError("Number of steps must be positive")
        if self.stabilization_time <= 0:
            raise ValueError("Stabilization time must be positive")
        for prob in probs:
            if not (0 <= prob <= 1):
                raise ValueError("Probability must be between 0 and 1")
