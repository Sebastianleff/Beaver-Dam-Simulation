"""Code for the simulation engine"""
import copy

import numpy as np

from beaver_dam_sim.simulation.models import RiverNetwork as River
from beaver_dam_sim.simulation.models import SimParam as Param
from beaver_dam_sim.simulation.models import SimulationStep as SimStep


class Simulation:
    _step: int
    """The current simulation step being processed"""

    _param: Param
    """The current simulation parameters"""

    _river: River
    """The River network being processed"""

    _history: list[SimStep]
    """List of steps taken in the simulation"""

    _rng: np.random.Generator
    """Seeded random number generator"""

    def __init__(self, param: Param, river: River):
        self._step = 0
        self._param = param
        self._river = river
        self._history = []
        self._rng = np.random.default_rng(self._param.random_seed)

        self._save_step()
        self._simulate()

    @property
    def history(self) -> list[SimStep]:
        return self._history

    def _simulate(self) -> None:
        """Simulate the simulation"""

        for _ in range(self._param.steps):
            self._run_step()

    def _run_step(self) -> None:
        """Runs the next step in the simulation"""

        self._step += 1
        self._create_dams()
        self._break_dams()
        self._propagate_floods()
        self._stabilize_floods()
        self._save_step()

    def _create_dams(self) -> None:
        """Create new dams based on the dam creation probability"""

        for edge in self._river.edges:
            for cell in (c for c in edge.cells.values() if not c.dam and not c.flooded):
                if self._rng.random() < self._param.dam_creation_probability:
                    cell.create_dam(self._step)

    def _break_dams(self) -> None:
        """Break dams based on the dam break probability"""

        for edge in self._river.edges:
            for cell in (c for c in edge.cells.values() if c.dam):
                if self._rng.random() < self._param.dam_break_probability:
                    cell.dam.break_dam(self._step)

    def _propagate_floods(self) -> None:
        """Propagate floods based on the dam propagation probability"""

        for edge in self._river.edges:
            for cell in edge.cells.values():

                # Flood newly broken dams
                if (
                        cell.dam
                        and cell.dam.broken_step == self._step
                        and self._rng.random() < self._param.flood_probability
                ):
                    cell.flood(self._step)
                    continue

                # First cell doesn't have upstream cell, all logic past here uses upstream state
                if cell.position == 1:
                    continue

                up_stream_cell = edge.cells[cell.position - 1]
                if not up_stream_cell.flooded:
                    continue

                # Meadows block flood propagation
                if cell.dam and cell.dam.meadow:
                    continue

                if not cell.dam:
                    cell.flood(self._step)
                    continue

                # If there is a dam, then run chance to trigger cascade flood
                if cell.dam and self._rng.random() < self._param.flood_break_probability:
                    for position in range(cell.position, len(edge.cells) + 1):
                        lower_cell = edge.cells[position]
                        lower_cell.flood(self._step)
                        if lower_cell.dam:
                            lower_cell.dam.break_dam(self._step)
                            if lower_cell.dam.meadow:
                                lower_cell.dam.meadow = False
                    # All cells after a cascade break must be flooded and have dams broken
                    break

    def _stabilize_floods(self) -> None:
        """Stabilize flooded cells based on flooded time"""

        for edge in self._river.edges:
            for cell in edge.cells.values():
                if not cell.flooded:
                    continue

                if cell.flooded_time(self._step) >= self._param.stabilization_time:
                    cell.clear_flood()

    def _save_step(self) -> None:
        step = SimStep(copy.deepcopy(self._river), self._step)
        self._history.append(step)
