"""Bataille navale quantique -- interface graphique Pygame (2 joueurs en hotseat).

Ce fichier ne contient QUE l'affichage et la gestion des evenements clavier/souris.
Toute la logique de jeu (et le cote quantique) vit dans `battleship_model.py`.

Deroulement d'une partie (machine a etats, voir la methode `on_key`) :

    PLACEMENT(J1) --ENTER--> TRANSITION --SPACE--> PLACEMENT(J2) --ENTER-->
    TRANSITION --SPACE--> FIRING(J1) --clic--> (touche: rejoue | manque: TRANSITION)
    ... jusqu'a ce qu'une flotte soit entierement coulee --> GAMEOVER

L'ecran de TRANSITION sert a cacher la flotte d'un joueur avant de passer la main
a l'autre (indispensable en hotseat, ou les deux jouent sur le meme ecran).
"""

import sys

import pygame

from battleship_model import GRID, Board

# geometrie de la fenetre
CELL = 64  # taille d'une case en pixels
MARGIN = 40  # marge autour de la grille
TOP = 90  # hauteur reservee au titre en haut
GRID_PX = GRID * CELL  # cote de la grille en pixels
W = max(MARGIN * 2 + GRID_PX, 620)  # largeur fenetre (min. 620 pour les titres)
H = TOP + GRID_PX + 120  # hauteur fenetre (grille + zone de texte)
GRID_X = (W - GRID_PX) // 2  # abscisse du bord gauche de la grille (centree)

# couleurs (R, V, B)
SEA = (30, 60, 110)  # fond d'une case (mer)
LINE = (20, 40, 80)  # quadrillage
SHIP_COLORS = [  # une couleur par navire, pour les distinguer
    (120, 200, 255),  # bleu
    (255, 175, 85),  # orange
    (150, 230, 150),  # vert
    (230, 150, 230),  # violet
    (240, 225, 120),  # jaune
]
HIT = (220, 60, 60)  # marqueur "touche"
MISS = (200, 220, 240)  # marqueur "manque"
TEXT = (235, 240, 250)  # texte principal
DIM = (150, 165, 185)  # texte secondaire (aide)
BG = (12, 20, 36)  # fond de la fenetre


def cell_rect(r, c):
    """Rectangle pixel de la case (ligne r, colonne c)."""
    return pygame.Rect(GRID_X + c * CELL, TOP + r * CELL, CELL, CELL)


def cell_at(pos):
    """Case (r, c) sous le curseur a la position pixel `pos`, ou None si hors grille."""
    x, y = pos
    if GRID_X <= x < GRID_X + GRID_PX and TOP <= y < TOP + GRID_PX:
        return (y - TOP) // CELL, (x - GRID_X) // CELL
    return None


class Game:
    """Etat global de la partie + boucle d'affichage/evenements."""

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("Bataille navale quantique")
        # trois tailles de police reutilisees partout
        self.font = pygame.font.SysFont("consolas", 22)
        self.big = pygame.font.SysFont("consolas", 30, bold=True)
        self.small = pygame.font.SysFont("consolas", 16)

        # une grille (flotte) par joueur ; on genere deja un placement aleatoire
        self.boards = [Board(), Board()]
        self.boards[0].place_random_superposed()
        self.boards[1].place_random_superposed()

        # variables d'etat de la machine a etats
        self.phase = "PLACEMENT"  # PLACEMENT | TRANSITION | FIRING | GAMEOVER
        self.current = 0  # index du joueur actif (0 ou 1)
        self.placed = [False, False]  # chaque joueur a-t-il valide son placement ?
        self.next_phase = None  # phase visee une fois la TRANSITION passee
        self.pending_player = 0  # joueur qui prendra la main apres la TRANSITION
        self.message = ""  # feedback du dernier tir, affiche en bas
        self.winner = None  # index du gagnant une fois la partie finie

    def _draw_grid(self):
        """Dessine le quadrillage vide (la mer)."""
        for r in range(GRID):
            for c in range(GRID):
                pygame.draw.rect(self.screen, SEA, cell_rect(r, c))
                pygame.draw.rect(self.screen, LINE, cell_rect(r, c), 1)

    def _draw_own(self, board):
        """Vue 'ma flotte' : on voit ses propres navires.

        Chaque navire a une couleur et un numero. Un navire en superposition
        occupe DEUX groupes de cases (positions A et B) de meme couleur/numero :
        c'est cette double occupation qui materialise la superposition a l'ecran.
        Un navire deja mesure n'occupe plus qu'un seul groupe (sa position reelle).
        """
        for i, s in enumerate(board.ships):
            col = SHIP_COLORS[i % len(SHIP_COLORS)]
            label = str(i + 1)
            if s.collapsed is None:
                # navire fantome : cases semi-transparentes + bordure + numero
                fill = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
                fill.fill((*col, 90))  # 90 = alpha (translucide)
                # bord blanc epais si le navire est intrique (sinon bord couleur)
                entangled = s.partner is not None
                border = (255, 255, 255) if entangled else col
                for r, c in s.candidate_cells():
                    rect = cell_rect(r, c)
                    self.screen.blit(fill, rect.topleft)
                    pygame.draw.rect(self.screen, border, rect, 3 if entangled else 2)
                    self._center_label(label, rect)
            else:
                # navire effondre : cases pleines, position reelle
                for r, c in s.footprint():
                    rect = cell_rect(r, c)
                    pygame.draw.rect(self.screen, col, rect)
                    pygame.draw.rect(self.screen, LINE, rect, 1)
                    self._center_label(label, rect)
        # par-dessus, les tirs deja recus (touche / manque)
        for (r, c), res in board.shots.items():
            self._mark(r, c, res)

    def _draw_fog(self, board):
        """Vue 'grille adverse'.

        On ne voit PAS les navires ennemis, seulement le resultat de ses propres
        tirs passes (touche / manque).
        """
        for (r, c), res in board.shots.items():
            self._mark(r, c, res)

    def _center_label(self, text, rect):
        """Ecrit un petit texte blanc centre dans une case."""
        img = self.small.render(text, True, (255, 255, 255))
        self.screen.blit(img, img.get_rect(center=rect.center))

    def _mark(self, r, c, res):
        """Marqueur d'un tir : gros rond rouge = touche, petit rond clair = manque."""
        cx, cy = cell_rect(r, c).center
        if res == "hit":
            pygame.draw.circle(self.screen, HIT, (cx, cy), CELL // 3)
        else:
            pygame.draw.circle(self.screen, MISS, (cx, cy), CELL // 6)

    def _text(self, s, y, font=None, color=TEXT, center=True):
        """Affiche une ligne de texte a l'ordonnee y.

        Garde-fou : si le texte est plus large que la fenetre, on le retrecit
        pour qu'il tienne (evite tout debordement hors de l'ecran).
        """
        font = font or self.font
        img = font.render(s, True, color)
        maxw = W - 2 * MARGIN
        if img.get_width() > maxw:
            new_h = int(img.get_height() * maxw / img.get_width())
            img = pygame.transform.smoothscale(img, (maxw, new_h))
        rect = img.get_rect()
        if center:
            rect.midtop = (W // 2, y)
        else:
            rect.topleft = (MARGIN, y)
        self.screen.blit(img, rect)

    def draw(self):
        """Redessine tout l'ecran selon la phase courante."""
        self.screen.fill(BG)
        p = self.current + 1  # numero du joueur (1 ou 2) pour l'affichage

        if self.phase == "TRANSITION":
            # ecran neutre : cache la flotte du joueur precedent
            self._text(f"Au tour du Joueur {p}", H // 2 - 40, self.big)
            self._text("(cachez l'ecran de l'adversaire)", H // 2, self.font, DIM)
            self._text("ESPACE pour continuer", H // 2 + 40, self.font, DIM)
            pygame.display.flip()
            return

        if self.phase == "PLACEMENT":
            self._text(f"Joueur {p} -- placement de la flotte", 20, self.big)
            self._draw_grid()
            self._draw_own(self.boards[self.current])
            self._text(
                "R = relancer le placement   ENTER = valider",
                TOP + GRID_PX + 20,
                self.small,
                DIM,
            )
            self._text(
                "Chaque couleur/numero = 1 navire et ses 2 positions possibles",
                TOP + GRID_PX + 44,
                self.small,
                DIM,
            )
            # legende des navires intriques (bord blanc)
            ent = [
                str(i + 1)
                for i, s in enumerate(self.boards[self.current].ships)
                if s.partner is not None
            ]
            if ent:
                self._text(
                    f"Navires N.{' et N.'.join(ent)} intriques (bord blanc) : "
                    "toucher l'un fige l'autre",
                    TOP + GRID_PX + 68,
                    self.small,
                    DIM,
                )

        elif self.phase == "FIRING":
            target = self.boards[1 - self.current]  # on tire sur la flotte adverse
            self._text(f"Joueur {p} -- tirez sur la flotte adverse", 20, self.big)
            self._draw_grid()
            self._draw_fog(target)
            hint = self.message or "Cliquez une case pour tirer (= mesure quantique)"
            self._text(hint, TOP + GRID_PX + 20, self.font)
            remaining = sum(not s.is_sunk() for s in target.ships)
            self._text(
                f"Navires adverses restants : {remaining}",
                TOP + GRID_PX + 54,
                self.small,
                DIM,
            )

        elif self.phase == "GAMEOVER":
            self._draw_grid()
            self._draw_fog(self.boards[1 - self.winner])
            self._text(f"Joueur {self.winner + 1} a gagne !", 20, self.big, HIT)
            self._text("Echap pour quitter", TOP + GRID_PX + 20, self.font, DIM)

        pygame.display.flip()

    #  MACHINE A ETATS
    def _go_transition(self, next_phase, next_player):
        """Passe par l'ecran de transition avant de rendre la main a `next_player`."""
        self.next_phase = next_phase
        self.pending_player = next_player
        self.phase = "TRANSITION"

    def on_key(self, key):
        """Gere une touche selon la phase courante."""
        if self.phase == "TRANSITION" and key == pygame.K_SPACE:
            # le joueur suivant a pris le controle : on entre dans la phase visee
            self.current = self.pending_player
            self.phase = self.next_phase
            self.message = ""

        elif self.phase == "PLACEMENT":
            if key == pygame.K_r:
                # relance un placement aleatoire tant qu'il ne convient pas
                self.boards[self.current].place_random_superposed()
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.placed[self.current] = True
                if not self.placed[1 - self.current]:
                    self._go_transition(
                        "PLACEMENT", 1 - self.current
                    )  # au tour de l'autre de placer
                else:
                    self._go_transition(
                        "FIRING", 0
                    )  # les deux ont place -> phase de tir

        elif self.phase == "GAMEOVER" and key == pygame.K_ESCAPE:
            pygame.quit()
            sys.exit()

    def on_click(self, pos):
        """Gere un clic gauche : tirer sur la case visee (uniquement en phase FIRING)."""
        if self.phase != "FIRING":
            return
        cell = cell_at(pos)
        if cell is None:
            return

        target = self.boards[1 - self.current]
        res = target.fire(cell)  # la mesure quantique (cote modele)

        if res == "repeat":
            self.message = "Deja tire ici."
            return
        if target.all_sunk():  # derniere case coulee -> victoire
            self.winner = self.current
            self.phase = "GAMEOVER"
            return

        # si le tir a mesure un navire intrique, son partenaire vient d'etre fige aussi
        note = (
            " | Intrication : le navire lie est aussi fige !"
            if target.last_entangled
            else ""
        )
        label = {"hit": "TOUCHE !", "miss": "manque.", "sunk": "COULE !"}[res]
        if res in ("hit", "sunk"):
            # touche : on garde la main, on peut retirer immediatement
            self.message = f"{label} Rejouez !{note}"
        else:
            # manque : on montre le resultat puis on passe la main via la transition
            self.message = f"{label} (au tour de l'adversaire){note}"
            self.draw()
            pygame.time.wait(1200 if note else 650)  # pause plus longue si intrication
            self._go_transition("FIRING", 1 - self.current)

    #  BOUCLE PRINCIPALE
    def run(self):
        clock = pygame.time.Clock()
        while True:
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                elif e.type == pygame.KEYDOWN:
                    self.on_key(e.key)
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    self.on_click(e.pos)
            self.draw()
            clock.tick(60)  # 60 images par seconde max


if __name__ == "__main__":
    Game().run()
