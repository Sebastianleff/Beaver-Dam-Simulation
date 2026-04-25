from unittest import TestCase
from unittest.mock import patch, Mock

from beaver_dam_sim.simulation import Simulation, SimParam, SimulationStep, RiverNetwork

def make_param(**overrides):
    data = {
        "dam_creation_probability": 0.0,
        "dam_break_probability": 0.0,
        "flood_probability": 0.0,
        "flood_break_probability": 0.0,
        "stabilization_time": 3,
        "steps": 1,
        "random_seed": 123,
        "meadow_probability": 0.0,
    }
    data.update(overrides)
    return SimParam(**data)

def make_river():
    river = RiverNetwork()
    river.add_node()
    river.add_node()
    river.add_edge(0,1)
    return river

def arrange_river_full():
    river = make_river()

    edge = river.edges[0]
    edge.cells[2].create_dam(3)

    edge.cells[3].create_dam(4)
    edge.cells[3].dam.break_dam(5)

    edge.cells[4].flood(5)
    edge.cells[5].flood(5)
    edge.cells[6].flood(5)

    edge.cells[7].create_dam(3)
    edge.cells[7].dam.break_dam(3)
    edge.cells[7].dam.make_meadow()

    edge.cells[9].create_dam(3)

    return river


class TestSimulation(TestCase):

    def test_create_dams(self):
        river = arrange_river_full()

        with patch.object(Simulation, "_simulate", return_value=None):
            sim = Simulation(make_param(dam_creation_probability=0.5), river)

        sim._step = 1
        sim._rng = Mock()
        sim._rng.random.return_value = 0.1

        sim._create_dams()

        edge = sim._river.edges[0]

        for cell_id, cell in edge.cells.items():
            # dam is already existent and in same state as arranged
            if cell_id in [2, 3, 7, 9]:
                self.assertIsNotNone(cell.dam)
                if cell_id in [2, 9]:
                    self.assertFalse(cell.dam.broken)
                if cell_id == 3:
                    self.assertTrue(cell.dam.broken)
                if cell_id == 7:
                    self.assertTrue(cell.dam.broken and cell.dam.meadow)

            # should not put dams on flooded cells
            elif cell_id in [4, 5, 6]:
                self.assertIsNone(cell.dam)

            #all other cells should have new intact dams
            else:
                self.assertIsNotNone(cell.dam)
                self.assertEqual(cell.dam.created_step, 1)
                self.assertFalse(cell.dam.broken)

    def test_break_dams(self):
        river = arrange_river_full()

        with patch.object(Simulation, "_simulate", return_value=None):
            sim = Simulation(make_param(dam_break_probability=0.5), river)

        sim._step = 1
        sim._rng = Mock()
        sim._rng.random.return_value = 0.1

        sim._break_dams()

        edge = sim._river.edges[0]

        for cell_id, cell in edge.cells.items():
            # broken dams and meadows stay in state
            if cell_id in [3, 7]:
                self.assertIsNotNone(cell.dam)
                if cell_id == 3:
                    self.assertTrue(cell.dam.broken)
                    self.assertTrue(cell.dam.broken_step == 5)
                if cell_id == 7:
                    self.assertTrue(cell.dam.broken and cell.dam.meadow)

            # unbroken dams should now be broken
            elif cell_id in [2, 9]:
                self.assertTrue(cell.dam.broken)
                self.assertTrue(cell.dam.broken_step == 1)

            #all other cells should have no dam
            else:
                self.assertIsNone(cell.dam)

    def test_propagate_flood_dam(self):
        river = make_river()
        edge = river.edges[0]

        edge.cells[2].create_dam(3)
        edge.cells[2].dam.break_dam(4)

        with patch.object(Simulation, "_simulate", return_value=None):
            sim = Simulation(make_param(flood_probability=0.5), river)

        sim._step = 4
        sim._rng = Mock()
        sim._rng.random.return_value = 0.1

        sim._propagate_floods()

        self.assertTrue(sim._river.edges[0].cells[3].flooded)

    def test_propagate_flood_open_cell(self):
        river = make_river()
        edge = river.edges[0]

        edge.cells[2].flood(4)

        with patch.object(Simulation, "_simulate", return_value=None):
            sim = Simulation(make_param(), river)

        sim._step = 4
        sim._propagate_floods()

        self.assertTrue(edge.cells[3].flooded)

    def test_propagate_flood_blocked_meadow(self):
        river = make_river()
        edge = river.edges[0]

        edge.cells[2].flood(4)
        edge.cells[6].create_dam(3)
        edge.cells[6].dam.break_dam(5)
        edge.cells[6].dam.make_meadow()

        with patch.object(Simulation, "_simulate", return_value=None):
            sim = Simulation(make_param(), river)

        sim._step = 4
        sim._propagate_floods()

        for cell_id, cell in edge.cells.items():
            if cell_id in [2, 3, 4, 5]:
                self.assertTrue(cell.flooded)
            else:
                self.assertFalse(cell.flooded)

    def test_propagate_flood_blocked_dam(self):
        river = make_river()
        edge = river.edges[0]

        edge.cells[2].flood(4)
        edge.cells[6].create_dam(3)

        with patch.object(Simulation, "_simulate", return_value=None):
            sim = Simulation(make_param(), river)

        sim._step = 4
        sim._propagate_floods()

        for cell_id, cell in edge.cells.items():
            if cell_id in [2, 3, 4, 5]:
                self.assertTrue(cell.flooded)
            else:
                self.assertFalse(cell.flooded)

    def test_propagate_flood_cascade(self):
        river = make_river()
        edge = river.edges[0]

        edge.cells[2].flood(4)
        edge.cells[6].create_dam(3)
        edge.cells[8].create_dam(3)

        with patch.object(Simulation, "_simulate", return_value=None):
            sim = Simulation(make_param(flood_break_probability=0.5), river)

        sim._step = 4
        sim._rng = Mock()
        sim._rng.random.return_value = 0.1
        sim._propagate_floods()

        for cell_id, cell in edge.cells.items():
            if cell_id in [2, 3, 4, 5, 6, 7, 8, 9, 10]:
                self.assertTrue(cell.flooded)
            if cell_id in [6, 8]:
                self.assertTrue(cell.dam.broken)
            if cell_id == 1:
                self.assertFalse(cell.flooded)
