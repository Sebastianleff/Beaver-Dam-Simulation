"""Services for UI to run, manage and validate Simulations"""
import copy
import csv

from beaver_dam_sim.simulation import SimulationStep, SimParam, Simulation, RiverNetwork

# Validation Service
class ValidationService:
    @staticmethod
    def validate_params(params: SimParam) -> bool:
        if not (0 <= params.dam_creation_probability <= 1):
            return False
        if not (0 <= params.dam_break_probability <= 1):
            return False
        if not (0 <= params.flood_probability <= 1):
            return False
        if not (0 <= params.flood_break_probability <= 1):
            return False
        if params.stabilization_time <= 0:
            return False
        if params.steps <= 0:
            return False
        return True


# CSV Service
class CSVService:

    @staticmethod
    def load_sim_params(file_path: str) -> list[SimParam]:
        params_list = []

        with open(file_path, newline="") as csvfile:
            reader = csv.DictReader(csvfile)

            for row in reader:
                params_list.append(
                    SimParam(
                        dam_creation_probability=float(row["dam_creation_probability"]),
                        dam_break_probability=float(row["dam_break_probability"]),
                        flood_probability=float(row["flood_probability"]),
                        flood_break_probability=float(row["flood_break_probability"]),
                        stabilization_time=int(row["stabilization_time"]),
                        steps=int(row["years"]),
                        random_seed=int(row["random_seed"]),
                        meadow_probability=float(row["meadow_probability"])
                    )
                )

        return params_list

    @staticmethod
    def save_sim_results(file_path: str, results: list[list]) -> None:

        with open(file_path, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)

            writer.writerow(["simulation_id", "year", "cells_flooded", "dams_created", "dams_broken"])

            for sim_id, history in enumerate(results, 1):
                for step in history:
                    writer.writerow([
                        sim_id,
                        step.step,
                        len(step.cells_flooded),
                        len(step.dams_created),
                        len(step.dams_broken)
                    ])


# RiverNetwork Factory
class RiverNetworkFactory:

    @staticmethod
    def create_default_network() -> RiverNetwork:
        network = RiverNetwork()

        for _ in range(8):
            network.add_node()

        network.add_edge(5, 1)
        network.add_edge(5,2)
        network.add_edge(6, 3)
        network.add_edge(6,4)
        network.add_edge(7, 5)
        network.add_edge(7,6)
        network.add_edge(8,7)

        return network

class RiverNetworkBuilder:
    """Build custom river networks from user input."""

    @staticmethod
    def create_network(node_count: int, edges: list[tuple[int, int]]) -> RiverNetwork:
        if node_count <= 0:
            raise ValueError("node_count must be positive")

        network = RiverNetwork()

        for _ in range(node_count):
            network.add_node()

        for down, up in edges:

            # VALIDATION
            if down < 1 or down > node_count:
                raise ValueError(f"Invalid downstream node: {down}")

            if up < 1 or up > node_count:
                raise ValueError(f"Invalid upstream node: {up}")

            network.add_edge(down, up)

        return network

class SimulationService:
    """Interface for UI to run Simulations """

    def __init__(self):
        self.validation_service = ValidationService()
        self.csv_service = CSVService()
        self.factory = RiverNetworkFactory()

    def create_river(self, node_count: int, edges: list[tuple[int, int]]) -> RiverNetwork:
        """
        UI-facing API for creating custom river networks.
        """
        return RiverNetworkBuilder.create_network(node_count, edges)

    def run_simulation(self, params: SimParam, river: RiverNetwork = None) -> list[SimulationStep]:

        if not self.validation_service.validate_params(params):
            raise ValueError("Invalid simulation parameters")
        if river is None:
            river = self.factory.create_default_network()

        assert(isinstance(river, RiverNetwork))

        sim = Simulation(params, river)

        return sim.history

    def run_simulation_batch(self, input_file: str, output_file: str, river: RiverNetwork = None) -> None:

        params_list = self.csv_service.load_sim_params(input_file)

        for params in params_list:
            if not self.validation_service.validate_params(params):
                raise ValueError("Invalid simulation parameters")

        if river is None:
            river = self.factory.create_default_network()

        assert(isinstance(river, RiverNetwork))

        all_results: list[list] = []

        for params in params_list:
            sim = Simulation(params, copy.deepcopy(river))
            all_results.append(sim.history)

        self.csv_service.save_sim_results(output_file, all_results)