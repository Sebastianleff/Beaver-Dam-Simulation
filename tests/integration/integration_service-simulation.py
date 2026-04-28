import csv
import os
import tempfile
import unittest

from beaver_dam_sim.service import SimulationService, RiverNetworkFactory
from beaver_dam_sim.simulation import SimParam


class TestSimulationService(unittest.TestCase):

    def test_single_simulation_runs(self):
        service = SimulationService()

        params = SimParam(
            dam_creation_probability=0.5,
            dam_break_probability=0.5,
            flood_probability=0.5,
            flood_break_probability=0.5,
            stabilization_time=3,
            steps=5,
            random_seed=1,
            meadow_probability=0.5
        )

        history = service.run_simulation(params)

        self.assertIsInstance(history, list)
        self.assertGreaterEqual(len(history), 0)

    def test_single_simulation_runs_invalid(self):
        service = SimulationService()

        params = SimParam(
            dam_creation_probability=0.5,
            dam_break_probability=0.5,
            flood_probability=0.5,
            flood_break_probability=0.5,
            stabilization_time=3,
            steps=5,
            random_seed=1,
            meadow_probability=0.5
        )

        params.steps = -1
        params.dam_creation_probability = 1234

        self.assertRaises(ValueError, service.run_simulation, params)


    def test_batch_simulation_creates_output_file(self):
        service = SimulationService()

        with tempfile.TemporaryDirectory() as tmp:

            input_file = os.path.join(tmp, "input.csv")
            output_file = os.path.join(tmp, "output.csv")

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
                writer.writerow([0.1, 0.1, 0.1, 0.1, 3, 5, 1, 0.5])
                writer.writerow([0.2, 0.2, 0.2, 0.2, 5, 7, 2, 1])

            service.run_simulation_batch(input_file, output_file)

            self.assertTrue(os.path.exists(output_file))


if __name__ == '__main__':
    unittest.main()
