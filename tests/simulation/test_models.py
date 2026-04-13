from unittest import TestCase

from beaver_dam_sim.simulation.models import RiverEdge, RiverNode


class TestRiverEdge(TestCase):
    def test_post_init_creates_cells_with_expected_shape(self):
        down = RiverNode()
        up = RiverNode()

        edge = RiverEdge(down_stream_node=down, up_stream_node=up, length=30)

        self.assertEqual(len(edge.cells), 3)
        self.assertEqual(list(edge.cells.keys()), [1, 2, 3])

        positions = [cell.position for cell in edge.cells.values()]
        self.assertEqual(positions, [1, 2, 3])

        self.assertTrue(all(cell.edge is edge for cell in edge.cells.values()))
