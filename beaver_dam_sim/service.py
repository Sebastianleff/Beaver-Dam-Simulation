# service.py (UI / Application Service Layer)

from typing import List, Optional
import random
import csv

from models import SimParam, SimulationStep, RiverNetwork, Dam
from simulation_service import SimulationService  # your engine wrapper


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
        if params.years <= 0:
            return False
        return True


# CSV Service
class CSVService:

    @staticmethod
    def load_sim_params(file_path: str) -> List[SimParam]:
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
                        years=int(row["years"]),
                        random_seed=int(row["random_seed"]) if row.get("random_seed") else None
                    )
                )

        return params_list

    @staticmethod
    def save_sim_results(file_path: str, results: List[SimulationStep]) -> None:

        with open(file_path, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)

            writer.writerow(["year", "cells_flooded", "dams_created", "dams_broken"])

            for step in results:
                writer.writerow([
                    step.year,
                    len(step.cells_flooded),
                    len(step.dams_created),
                    len(step.dams_broken)
                ])


# RiverNetwork Factory
class RiverNetworkFactory:

    @staticmethod
    def create_network() -> RiverNetwork:
        network = RiverNetwork()

        # Example simple graph
        nodes = [RiverNetwork.Node() for _ in range(10)]  # adjust if needed

        network.nodes.extend(nodes)

        for i in range(len(nodes) - 1):
            edge = RiverNetwork.Edge(
                down_stream_node=nodes[i],
                up_stream_node=nodes[i + 1]
            )
            network.edges.append(edge)

        return network


# UI Application Service
class AppService:
    """
    UI-facing service layer.
    Only coordinates between UI and SimulationService.
    """

    def __init__(self):
        self.simulation_service = SimulationService()
        self.validation_service = ValidationService()
        self.csv_service = CSVService()
        self.factory = RiverNetworkFactory()


    # REQUIRED MAIN FUNCTION
    def run_simulation(self, params: SimParam) -> List[SimulationStep]:

        if not self.validation_service.validate_params(params):
            raise ValueError("Invalid simulation parameters")

        return self.simulation_service.run_simulation(params)

    
    # BATCH SIMULATION
    def run_simulation_batch(self, input_file: str, output_file: str) -> None:

        params_list = self.csv_service.load_sim_params(input_file)

        all_results: List[SimulationStep] = []

        for params in params_list:
            results = self.simulation_service.run_simulation(params)
            all_results.extend(results)

        self.csv_service.save_sim_results(output_file, all_results)