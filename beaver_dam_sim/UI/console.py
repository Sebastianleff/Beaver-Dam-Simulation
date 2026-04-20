"""Simple console UI for running beaver dam simulations."""

from beaver_dam_sim.service import SimulationService
from beaver_dam_sim.simulation import SimParam, SimulationStep


def ask_text(prompt: str) -> str:
    """Ask the user to enter text"""
    value = input(prompt).strip()
    while not value:
        print("Please enter a value.")
        value = input(prompt).strip()
    return value

def ask_int(prompt: str, minimum: int | None = None) -> int:
    """Ask the user to enter a number."""
    while True:
        raw = input(prompt).strip()
        try:
            value = int(raw)
            if minimum is not None and value < minimum:
                print(f"Please enter a number >= {minimum}.")
                continue
            return value
        except ValueError:
            print("Please enter a whole number.")

def ask_percent(prompt: str) -> float:
    """Ask the user for a percentage from 0 to 100 and return it as 0.0 to 1.0."""
    while True:
        raw = input(prompt).strip()
        try:
            value = float(raw)
            if value < 0 or value > 100:
                print("Please enter a percentage from 0 to 100.")
                continue
            return value / 100.0
        except ValueError:
            print("Please enter a number.")

def format_step(step: SimulationStep) -> None:
    """Format the simulation step for display."""
    print(f"Step {step.step}")
    print(f"Flooded cells: {len(step.cells_flooded)}")
    print(f"Dams created: {len(step.dams_created)}")
    print(f"Dams broken: {len(step.dams_broken)}")

def page(history: list[SimulationStep]) -> None:
    """Page through history to see each step"""
    if not history:
        print("No simulation steps to show.")
        return

    index = 0
    while True:
        print()
        print("=" * 40)
        print(f"Viewing step {index + 1} of {len(history)}")
        print("=" * 40)
        format_step(history[index])

        print()
        print("Commands:")
        print("n = next step")
        print("p = previous step")
        print("q = quit viewing")
        choice = input("> ").strip().lower()

        if choice == "n":
            if index < len(history) - 1:
                index += 1
            else:
                print("Already at the last step.")
        elif choice == "p":
            if index > 0:
                index -= 1
            else:
                print("Already at the first step.")
        elif choice == "q":
            break
        else:
            print("Please enter n, p, or q.")

def run_single_simulation(service: SimulationService) -> None:
    """Run a single simulation."""
    print()
    print("=== Single Simulation ===")
    dam_creation_probability = ask_percent("Dam creation probability (0-100%): ")
    dam_break_probability = ask_percent("Dam break probability (0-100%): ")
    flood_probability = ask_percent("Flood probability (0-100%): ")
    flood_break_probability = ask_percent("Flood break probability (0-100%): ")
    stabilization_time = ask_int("Stabilization time (positive whole number): ", 1)
    steps = ask_int("Number of steps (positive whole number): ", 1)
    random_seed = ask_int("Random seed (whole number): ")
    meadow_probability = ask_percent("Meadow probability (0-100%): ")

    params = SimParam(
        dam_creation_probability=dam_creation_probability,
        dam_break_probability=dam_break_probability,
        flood_probability=flood_probability,
        flood_break_probability=flood_break_probability,
        stabilization_time=stabilization_time,
        steps=steps,
        random_seed=random_seed,
        meadow_probability=meadow_probability,
    )

    history = service.run_simulation(params, None)
    page(history)

def run_batch_simulation(service: SimulationService) -> None:
    """Run a batch simulation."""
    print()
    print("=== Batch Simulation ===")
    print(f"\033[1mPlease use absolute path\033[0m")
    input_file = ask_text("Input CSV file path: ")
    output_file = ask_text("Output CSV file path: ")

    service.run_simulation_batch(input_file, output_file, None)

    print()
    print("Batch simulation complete.")
    print(f"Input file: {input_file}")
    print(f"Output file: {output_file}")

def main() -> None:
    service = SimulationService()

    print("Beaver Dam Simulation")
    print("=====================")

    while True:
        print()
        print("Choose an option:")
        print("1) Run a single simulation")
        print("2) Run a batch simulation")
        print("3) Quit")

        choice = input("> ").strip()

        if choice == "1":
            try:
                run_single_simulation(service)
            except ValueError as e:
                print(f"Error: {e}")
        elif choice == "2":
            try:
                run_batch_simulation(service)
            except OSError as e:
                print(f"Error: {e}")
        elif choice == "3":
            print("Goodbye.")
            break
        else:
            print("Please choose 1, 2, or 3.")


if __name__ == "__main__":
    main()
