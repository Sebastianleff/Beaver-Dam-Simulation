from collections import deque
from unittest import TestCase
from beaver_dam_sim.simulation.models import RiverEdge, RiverNode, RiverNetwork
from collections.abc import Callable
from itertools import count

def make_counter(start: int = 1) -> Callable[[], int]:
    values = count(start)
    return lambda: next(values)

class TestRiverEdge(TestCase):
    def test_post_init_creates_cells_with_expected_shape(self):

        down = RiverNode(1)
        up = RiverNode(2)

        cell_counter = make_counter()
        dam_counter = make_counter()

        edge = RiverEdge(down_stream_node=down, up_stream_node=up, length=30, id = 1, next_cell_id=cell_counter,
    next_dam_id=dam_counter )

        self.assertEqual(len(edge.cells), 3)
        self.assertEqual(list(edge.cells.keys()), [1, 2, 3])

        positions = [cell.position for cell in edge.cells.values()]
        self.assertEqual(positions, [1, 2, 3])

        self.assertTrue(all(cell.edge is edge for cell in edge.cells.values()))

class TestRiverNetwork(TestCase):
    def test_network_is_connected_as_a_graph(self):
        river = RiverNetwork()
        for _ in range(4):
            river.add_node()

        # graph representation
        # 2 3
        # |/
        # 1
        # |
        # 0

        river.add_edge(river.nodes[0], river.nodes[1])
        river.add_edge(river.nodes[1], river.nodes[2])
        river.add_edge(river.nodes[1], river.nodes[3])

        self.assertIs(river.terminal_node, river.nodes[0])

        self.assertIs(river.nodes[1].down_stream_edge, river.edges[0])
        self.assertEqual(river.nodes[0].up_stream_edge, [river.edges[0]])
        self.assertEqual(river.nodes[1].up_stream_edge, [river.edges[1], river.edges[2]])

        seen = []
        queue = deque([river.terminal_node])

        while queue:
            node = queue.popleft()
            seen.append(node)

            for edge in node.up_stream_edge or []:
                queue.append(edge.up_stream_node)

        self.assertEqual(seen, [river.nodes[0], river.nodes[1], river.nodes[2], river.nodes[3]])

    def test_shreve_order(self):
        river = RiverNetwork()
        for _ in range(10):
            river.add_node()

        # graph representation
        # 7 8 9
        #  \|/
        #   4 5 6
        #   |/ /
        #   2 3
        #   |/
        #   1
        #   |
        #   0

        river.add_edge(river.nodes[0], river.nodes[1])  # edge 0
        river.add_edge(river.nodes[1], river.nodes[2])  # edge 1
        river.add_edge(river.nodes[1], river.nodes[3])  # edge 2
        river.add_edge(river.nodes[2], river.nodes[4])  # edge 3
        river.add_edge(river.nodes[2], river.nodes[5])  # edge 4
        river.add_edge(river.nodes[3], river.nodes[6])  # edge 5
        river.add_edge(river.nodes[4], river.nodes[7])  # edge 6
        river.add_edge(river.nodes[4], river.nodes[8])  # edge 7
        river.add_edge(river.nodes[4], river.nodes[9])  # edge 8

        river.shreve_order()

        self.assertEqual([e.stream_order for e in river.edges], [5, 4, 1, 3, 1, 1, 1, 1, 1])
