"""Bataille navale quantique -- logique de jeu (sans aucune interface graphique).

IDEE CENTRALE
-------------
Dans une bataille navale classique, chaque navire occupe des cases fixes, cachees.
Ici, chaque navire est place en SUPERPOSITION sur DEUX empreintes candidates :
    - empreinte A  <-> etat |0> du qubit
    - empreinte B  <-> etat |1> du qubit
Tant que personne ne tire dessus, le navire est "fantome" : il est aux deux
endroits a la fois (50 % / 50 %).

Tirer sur une case fantome = MESURER le qubit du navire. La mesure effondre la
superposition sur A ou B (au hasard, 50/50, tire par Qiskit). Ensuite :
    - si l'empreinte retenue couvre la case visee  -> TOUCHE
    - sinon (le navire "etait" ailleurs)            -> MANQUE, et le navire est
      desormais classique (fige a sa position reelle).

Le circuit quantique se resume donc a UN qubit : H (superposition) puis measure.
Tout l'interet pedagogique est dans ce MAPPING quantique -> jeu, pas dans la
complexite du circuit (cf. conseils de l'enonce).
"""

import random

from qiskit import QuantumCircuit

from quantum_core import quantum_sample  # execute un circuit et renvoie les mesures

GRID = 6  # grille 6x6
SHIP_SIZES = [3, 2, 2]  # flotte : 1 navire de taille 3, puis 2 navires de taille 2


def _line(r, c, size, horizontal):
    """Cases d'un navire droit partant de (r, c). Renvoie None si ca sort de la grille."""
    cells = [(r, c + i) if horizontal else (r + i, c) for i in range(size)]
    if all(0 <= rr < GRID and 0 <= cc < GRID for rr, cc in cells):
        return tuple(cells)
    return None


def _random_placement(size):
    """Tire une empreinte droite (horizontale ou verticale) valide, au hasard."""
    while True:
        horizontal = random.random() < 0.5
        r = random.randrange(GRID)
        c = random.randrange(GRID)
        cells = _line(r, c, size, horizontal)
        if cells:  # on recommence tant que ca depasse la grille
            return cells


class Ship:
    """Un navire et ses deux positions possibles tant qu'il est en superposition.

    Attributs :
        size       : longueur du navire (nombre de cases)
        cand_a     : empreinte si le qubit s'effondre sur |0>
        cand_b     : empreinte si le qubit s'effondre sur |1>
        collapsed  : None (superpose) / "A" / "B" (une fois mesure)
        hits       : ensemble des cases deja touchees
        partner    : navire INTRIQUE a celui-ci (ou None) -- mesurer l'un mesure l'autre
    """

    def __init__(self, size, cand_a, cand_b):
        self.size = size
        self.cand_a = cand_a
        self.cand_b = cand_b
        self.collapsed = None
        self.hits = set()
        self.partner = None

    def footprint(self):
        """Cases reelles APRES effondrement, ou None si le navire est encore fantome."""
        if self.collapsed == "A":
            return self.cand_a
        if self.collapsed == "B":
            return self.cand_b
        return None

    def candidate_cells(self):
        """Toutes les cases fantomes (A + B) tant que le navire n'est pas mesure."""
        return set(self.cand_a) | set(self.cand_b)

    def is_sunk(self):
        """Vrai si le navire est effondre ET toutes ses cases reelles sont touchees."""
        fp = self.footprint()
        return fp is not None and self.hits.issuperset(fp)


class Board:
    """La flotte d'un joueur + l'historique des tirs recus sur cette flotte."""

    def __init__(self):
        self.ships = []
        self.shots = {}  # (r, c) -> "hit" | "miss" : memoire des tirs subis
        self.last_entangled = False  # le dernier tir a-t-il declenche une paire intriquee ?

    # ---- placement ---------------------------------------------------------
    def place_random_superposed(self):
        """Genere une flotte dont TOUTES les empreintes candidates sont disjointes.

        Pourquoi cette contrainte (aucune case partagee entre deux candidats) ?
        -> Ainsi, quelle que soit la facon dont les navires s'effondrent (A ou B),
           deux navires ne peuvent jamais se retrouver sur la meme case. On evite
           donc toute gestion de conflit au moment de l'effondrement : n'importe
           quelle combinaison de mesures donne un plateau valide.
        """
        for _ in range(500):  # au pire, on recommence toute la flotte
            self.ships = []
            occupied = set()  # cases deja reservees par un candidat
            ok = True
            for size in SHIP_SIZES:
                placed = False
                for _ in range(300):  # plusieurs essais pour ce navire
                    a = _random_placement(size)
                    b = _random_placement(size)
                    cells = set(a) | set(b)
                    # A et B doivent etre disjoints entre eux ET des autres navires
                    if len(cells) == 2 * size and cells.isdisjoint(occupied):
                        self.ships.append(Ship(size, a, b))
                        occupied |= cells
                        placed = True
                        break
                if not placed:  # navire impossible a caser -> on repart de zero
                    ok = False
                    break
            if ok:
                # INTRICATION : on lie les deux navires de taille 2 (index 1 et 2).
                # Des lors, tirer sur l'un mesure aussi l'autre (cf. _collapse).
                if len(self.ships) >= 3:
                    self.ships[1].partner = self.ships[2]
                    self.ships[2].partner = self.ships[1]
                return
        raise RuntimeError("placement impossible (grille trop petite ?)")

    # ---- consultation ------------------------------------------------------
    def _superposed_ship_at(self, cell):
        """Navire ENCORE fantome dont une empreinte candidate couvre `cell` (ou None).

        Grace a la contrainte de placement, au plus un navire correspond.
        """
        for s in self.ships:
            if s.collapsed is None and cell in s.candidate_cells():
                return s
        return None

    def _collapsed_ship_at(self, cell):
        """Navire DEJA effondre dont la position reelle couvre `cell` (ou None)."""
        for s in self.ships:
            fp = s.footprint()
            if fp is not None and cell in fp:
                return s
        return None

    def all_sunk(self):
        """Vrai si toute la flotte est coulee (condition de victoire adverse)."""
        return all(s.is_sunk() for s in self.ships)

    # ---- mesure quantique --------------------------------------------------
    @staticmethod
    def _bit_to_side(bit):
        """Traduit un bit mesure en position reelle : '0' -> A, '1' -> B."""
        return "A" if bit == "0" else "B"

    def _collapse(self, ship):
        """Effondre un navire fantome en MESURANT son qubit.

        Deux cas :

        - Navire SEUL (1 qubit) -- le coeur quantique du jeu :
              qc.h(0)    -> superposition egale (50 % |0>, 50 % |1>)
              qc.measure -> observe le qubit : le tir joue le role de l'observateur
          Le bit obtenu ('0'/'1') decide de la position reelle du navire (A ou B).

        - Navire INTRIQUE (2 qubits) -- si `ship.partner` est encore superpose :
              qc.h(0); qc.cx(0, 1)  -> etat de Bell |00>+|11> (les deux qubits corrELES)
              qc.measure([0,1])     -> resultat '00' ou '11' : les deux navires
                                       s'effondrent DU MEME cote (tous deux A ou tous deux B).
          Mesurer un seul tir fige donc les DEUX navires d'un coup : c'est l'intrication.
        """
        partner = ship.partner
        if partner is not None and partner.collapsed is None:
            qc = QuantumCircuit(2, 2)
            qc.h(0)
            qc.cx(0, 1)  # intrication : etat de Bell Phi+
            qc.measure([0, 1], [0, 1])
            bits = next(iter(quantum_sample(qc, shots=1)))  # ex. '00' ou '11'
            # Qiskit est little-endian : bits[-1] = qubit 0, bits[-2] = qubit 1
            ship.collapsed = self._bit_to_side(bits[-1])
            partner.collapsed = self._bit_to_side(bits[-2])
            self.last_entangled = True  # pour le feedback en jeu
        else:
            qc = QuantumCircuit(1, 1)
            qc.h(0)  # superposition
            qc.measure(0, 0)  # mesure = le tir observe le navire
            bit = next(iter(quantum_sample(qc, shots=1)))
            ship.collapsed = self._bit_to_side(bit)

    def fire(self, cell):
        """Tire sur une case. Renvoie 'repeat' | 'miss' | 'hit' | 'sunk'.

        Trois cas possibles :
          1. la case appartient a un navire deja effondre        -> touche classique
          2. la case appartient a un navire encore fantome       -> on le MESURE ;
             touche si l'effondrement tombe sur cette case, sinon manque
          3. la case ne couvre aucun navire                      -> manque
        """
        if cell in self.shots:  # on a deja tire ici
            return "repeat"

        self.last_entangled = False  # reinitialise le drapeau d'intrication
        collapsed = self._collapsed_ship_at(cell)  # cas 1 ?
        if collapsed is None:
            ghost = self._superposed_ship_at(cell)  # cas 2 ?
            if ghost is not None:
                self._collapse(ghost)  # <-- mesure quantique
                if cell in ghost.footprint():
                    collapsed = ghost  # effondre sur nous : touche
                # sinon : effondre a l'autre position -> la case visee est vide -> manque

        if collapsed is not None:
            collapsed.hits.add(cell)
            self.shots[cell] = "hit"
            return "sunk" if collapsed.is_sunk() else "hit"

        self.shots[cell] = "miss"  # cas 3 (ou cas 2 rate)
        return "miss"


# --------------------------------------------------------------------------
# Auto-verification (sans framework de test) : `python battleship_model.py`
# Chaque assert echoue bruyamment si la logique casse.
# --------------------------------------------------------------------------
if __name__ == "__main__":
    random.seed(0)

    # 1) placement : les empreintes candidates ne se chevauchent jamais
    b = Board()
    b.place_random_superposed()
    all_cells = [c for s in b.ships for c in s.candidate_cells()]
    assert len(all_cells) == len(set(all_cells)), "chevauchement de candidats !"

    # 2) l'effondrement est bien ~50/50 sur un grand nombre de mesures
    countA = 0
    N = 300
    for _ in range(N):
        s = Ship(2, ((0, 0), (0, 1)), ((3, 3), (3, 4)))
        Board()._collapse(s)
        countA += s.collapsed == "A"
    assert 0.35 * N < countA < 0.65 * N, f"pas 50/50 : {countA}/{N}"

    # 3) tirer hors de tout candidat = manque, et ne modifie aucun etat quantique
    b2 = Board()
    b2.ships = [Ship(2, ((0, 0), (0, 1)), ((5, 5), (5, 4)))]
    empty = next(
        (r, c)
        for r in range(GRID)
        for c in range(GRID)
        if (r, c) not in b2.ships[0].candidate_cells()
    )
    assert b2.fire(empty) == "miss"
    assert b2.ships[0].collapsed is None

    # 4) un navire finit coule quand on touche toute son empreinte effondree
    b3 = Board()
    ship = Ship(2, ((0, 0), (0, 1)), ((5, 5), (5, 4)))
    ship.collapsed = "A"  # on force l'effondrement sur A pour le test
    b3.ships = [ship]
    assert b3.fire((0, 0)) == "hit"
    assert b3.fire((0, 1)) == "sunk"
    assert b3.all_sunk()

    # 5) un tir repete au meme endroit est detecte
    assert b3.fire((0, 0)) == "repeat"

    # 6) INTRICATION : mesurer un navire mesure aussi son partenaire, et les deux
    #    issues sont TOUJOURS correlees (etat de Bell -> tous deux A ou tous deux B)
    for _ in range(50):
        s1 = Ship(2, ((0, 0), (0, 1)), ((5, 5), (5, 4)))
        s2 = Ship(2, ((2, 0), (2, 1)), ((3, 3), (3, 4)))
        s1.partner = s2
        s2.partner = s1
        bd = Board()
        bd._collapse(s1)  # on ne mesure QUE s1...
        assert s2.collapsed is not None, "le partenaire n'a pas ete effondre"
        assert s1.collapsed == s2.collapsed, "issues non correlees (intrication cassee)"
        assert bd.last_entangled is True

    # 7) la flotte generee lie bien deux navires par intrication
    bp = Board()
    bp.place_random_superposed()
    linked = [s for s in bp.ships if s.partner is not None]
    assert len(linked) == 2 and linked[0].partner is linked[1]

    print("battleship_model : tous les asserts passent OK")
