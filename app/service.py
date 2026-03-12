# services.py
from dataclasses import dataclass
from typing import List, Optional
import csv
import random

# ----- Data classes -----
@dataclass
class SimParam:
    dam_creation_prob: float
    dam_break_prob: float
    catastrophic_fail_prob: float
    downstream_break_prob: float
    river_stabilize_time: int
    duration_years: int
    random_seed: Optional[int] = None


@dataclass
class SimulationStep:
    year: int
    river_state: dict  # Replace with your RiverNetwork structure
    dams_state: dict   # Replace with dam info


# ----- Validation Service -----
class ValidationService:
    @staticmethod
    def validate_params(params: SimParam) -> bool:
        """Ensure parameters are within valid ranges."""
        if not (0 <= params.dam_creation_prob <= 1):
            return False
        if not (0 <= params.dam_break_prob <= 1):
            return False
        if not (0 <= params.catastrophic_fail_prob <= 1):
            return False
        if not (0 <= params.downstream_break_prob <= 1):
            return False
        if params.river_stabilize_time < 0:
            return False
        if params.duration_years <= 0:
            return False
        return True


# ----- CSV Service -----
class CSVService:
    @staticmethod
    def load_sim_params(file_path: str) -> List[SimParam]:
        """Load simulation parameters from CSV."""
        params_list = []
        with open(file_path, newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                params = SimParam(
                    dam_creation_prob=float(row['dam_creation_prob']),
                    dam_break_prob=float(row['dam_break_prob']),
                    catastrophic_fail_prob=float(row['catastrophic_fail_prob']),
                    downstream_break_prob=float(row['downstream_break_prob']),
                    river_stabilize_time=int(row['river_stabilize_time']),
                    duration_years=int(row['duration_years']),
                    random_seed=int(row['random_seed']) if row.get('random_seed') else None
                )
                params_list.append(params)
        return params_list

    @staticmethod
    def save_sim_results(file_path: str, results: List[SimulationStep]):
        """Save simulation results to CSV."""
        if not results:
            return
        with open(file_path, 'w', newline='') as csvfile:
            fieldnames = ['year', 'river_state', 'dams_state']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for step in results:
                writer.writerow({
                    'year': step.year,
                    'river_state': step.river_state,
                    'dams_state': step.dams_state
                })


# ----- RiverNetwork Factory -----
class RiverNetworkFactory:
    @staticmethod
    def create_network(num_nodes: int):
        """Create a river network graph with a given number of nodes."""
        network = {i: {'edges': [], 'dams': []} for i in range(num_nodes)}
        # Placeholder: link nodes sequentially
        for i in range(num_nodes - 1):
            network[i]['edges'].append(i + 1)
        return network


# ----- Simulation Service -----
class SimulationService:
    def __init__(self):
        self.validation_service = ValidationService()
        self.csv_service = CSVService()
        self.factory = RiverNetworkFactory()

    def run_simulation(self, params: SimParam) -> List[SimulationStep]:
        """Orchestrate the simulation."""
        if params.random_seed is not None:
            random.seed(params.random_seed)

        if not self.validation_service.validate_params(params):
            raise ValueError("Invalid simulation parameters!")

        # Create initial river network
        river_network = self.factory.create_network(num_nodes=10)  # Example: 10 nodes

        results = []
        for year in range(1, params.duration_years + 1):
            # Placeholder: simulate dam creation/breakage
            dams = {}
            for node, data in river_network.items():
                if random.random() < params.dam_creation_prob:
                    data['dams'].append(f"Dam_{year}_{node}")
                if data['dams'] and random.random() < params.dam_break_prob:
                    data['dams'].pop()  # Remove one dam
            # Record the step
            step = SimulationStep(
                year=year,
                river_state=river_network.copy(),
                dams_state={k: v['dams'][:] for k, v in river_network.items()}
            )
            results.append(step)

        return results


