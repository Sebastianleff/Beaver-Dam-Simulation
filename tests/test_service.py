import unittest
import tempfile
import csv
import os

from beaver_dam_sim.service import (
    ValidationService,
    CSVService,
    SimParam,
    RiverNetworkFactory
)


class TestValidationService(unittest.TestCase):

    def test_valid_params(self):
        params = SimParam(
            dam_creation_probability=0.5,
            dam_break_probability=0.5,
            flood_probability=0.5,
            flood_break_probability=0.5,
            stabilization_time=3,
            steps=10,
            random_seed=1,
            meadow_probability=0.5
        )

        self.assertTrue(ValidationService.validate_params(params))

    def test_validation_service_detects_invalid_after_creation(self):
        params = SimParam(
            dam_creation_probability=0.5,
            dam_break_probability=0.5,
            flood_probability=0.5,
            flood_break_probability=0.5,
            stabilization_time=3,
            steps=10,
            random_seed=1,
            meadow_probability=0.5
        )

        params.steps = -1
        params.dam_creation_probability = 1234

        self.assertFalse(ValidationService.validate_params(params))


class TestCSVService(unittest.TestCase):

    def test_csv_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:

            input_file = os.path.join(tmp, "input.csv")

            with open(input_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "dam_creation_probability",
                    "dam_break_probability",
                    "flood_probability",
                    "flood_break_probability",
                    "stabilization_time",
                    "years",
                    "random_seed",
                    "meadow_probability"
                ])
                writer.writerow([0.1, 0.2, 0.3, 0.4, 3, 5, 42, 0.5])
                writer.writerow([0.2, 0.2, 0.2, 0.2, 5, 7, 2, 1])

            params_list = CSVService.load_sim_params(input_file)

            self.assertEqual(len(params_list), 2)
            self.assertEqual(params_list[0].random_seed, 42)


class TestRiverNetworkFactory(unittest.TestCase):

    def test_create_default_network_has_expected_topology(self):
        network = RiverNetworkFactory.create_default_network()

        self.assertEqual(len(network.nodes), 8)
        self.assertEqual(len(network.edges), 7)

        actual_pairs = {(edge.down_stream_node, edge.up_stream_node) for edge in network.edges}
        expected_pairs = {
            (5, 1),
            (5, 2),
            (6, 3),
            (6, 4),
            (7, 5),
            (7, 6),
            (8, 7),
        }
        self.assertSetEqual(actual_pairs, expected_pairs)

if __name__ == "__main__":
    unittest.main()