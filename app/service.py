class SimulationService:
    def __init__(self):
        self.validation_service = ValidationService()
        self.factory = RiverNetworkFactory()

    def run_simulation(self, params: SimParam) -> List[SimulationStep]:

        if not self.validation_service.validate_params(params):
            raise ValueError("Invalid simulation parameters")

        if params.random_seed is not None:
            random.seed(params.random_seed)

        river_network = self.factory.create_network()

        results = []

        for year in range(params.years):

            for edge in river_network.edges:
                for cell in edge.cells.values():

                    if random.random() < params.dam_creation_probability:
                        if cell.dam is None:
                            cell.dam = Dam(cell=cell, created_year=year)

            step = SimulationStep(
                river_snapshot=river_network,
                year=year
            )

            results.append(step)

        return results