# quantum_core.py  ---  socle commun a tous les sujets
# Fourni par l'enonce, + repli BasicSimulator si qiskit-aer indisponible
# (utile sous Python 3.14 ou aer n'a pas toujours de wheel).
from qiskit import QuantumCircuit, transpile

try:
    from qiskit_aer import AerSimulator

    simulateur = AerSimulator()
except ImportError:
    # ponytail: repli pur-Python fourni avec qiskit, meme API .run().result()
    from qiskit.providers.basic_provider import BasicSimulator

    simulateur = BasicSimulator()


def quantum_sample(circuit, shots=1024):
    """Execute un circuit (avec mesures) et renvoie {bitstring: occurrences}."""
    tqc = transpile(circuit, simulateur)
    resultat = simulateur.run(tqc, shots=shots).result()
    return resultat.get_counts()


def quantum_bits(circuit, shots=1):
    """Renvoie une liste de bitstrings tires (pratique pour piloter du creatif)."""
    counts = quantum_sample(circuit, shots=shots)
    bits = []
    for bitstring, n in counts.items():
        bits.extend([bitstring] * n)
    return bits
