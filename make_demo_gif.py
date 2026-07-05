"""Genere `demo.gif` : une demo scriptee de la Bataille navale quantique.

Ce script NE fait PAS partie du jeu : il sert uniquement a produire le livrable
creatif (le GIF integre dans le markdown). Il rend les ecrans hors-fenetre (driver
SDL "dummy"), capture chaque scene, et les assemble en GIF avec Pillow.

Le scenario montre une partie complete : placement des deux flottes, tirs du Joueur 1
(touche -> rejoue, intrication, puis manque -> on passe la main), tour du Joueur 2,
retour au Joueur 1 qui coule la derniere flotte, puis l'ecran de victoire.

Lancer :  .\.venv\Scripts\python make_demo_gif.py
"""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")   # rendu hors-ecran
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import random

import pygame
from PIL import Image

import battleship_pygame as bp

GIF_PATH = "demo.gif"
GIF_WIDTH = 440                    # largeur du GIF (redimensionne pour rester leger)

frames = []                        # liste de (Image PIL, duree en ms)


def capture(duration_ms):
    """Dessine l'ecran courant et l'ajoute comme une frame du GIF."""
    g.draw()
    raw = pygame.image.tostring(g.screen, "RGB")
    img = Image.frombytes("RGB", g.screen.get_size(), raw)
    h = int(GIF_WIDTH * img.height / img.width)
    frames.append((img.resize((GIF_WIDTH, h)), duration_ms))


def water_cells(board):
    """Cases de pure eau (ne couvrant AUCUN navire), pour des manques garantis."""
    occupied = {c for s in board.ships for c in s.candidate_cells()}
    return [(r, c) for r in range(bp.GRID) for c in range(bp.GRID)
            if (r, c) not in occupied]


def hit_one(board, ship, n=1):
    """Fige un navire (cote A) et marque n de ses cases comme touchees."""
    if ship.collapsed is None:
        ship.collapsed = "A"
    for cell in ship.footprint()[:n]:
        board.shots[cell] = "hit"
        ship.hits.add(cell)


def add_misses(board, k):
    """Ajoute k marqueurs 'manque' sur des cases d'eau encore vierges."""
    free = [c for c in water_cells(board) if c not in board.shots]
    for cell in random.sample(free, min(k, len(free))):
        board.shots[cell] = "miss"


def sink_everything(board):
    """Coule toute la flotte : chaque navire fige et entierement touche."""
    for s in board.ships:
        hit_one(board, s, n=s.size)


# --- mise en place ----------------------------------------------------------
random.seed(7)                     # placement reproductible
g = bp.Game()
b1 = g.boards[1]                   # flotte visee par le Joueur 1
b0 = g.boards[0]                   # flotte visee par le Joueur 2

# 1) Placement du Joueur 1 : navires fantomes (2 positions) + paire intriquee
g.phase, g.current, g.message = "PLACEMENT", 0, ""
capture(1700)

# 2) Transition vers le Joueur 2
g.phase, g.pending_player, g.next_phase = "TRANSITION", 1, "PLACEMENT"
capture(1000)

# 3) Placement du Joueur 2
g.phase, g.current = "PLACEMENT", 1
capture(1700)

# 4) Transition vers la phase de tir
g.phase, g.pending_player, g.next_phase = "TRANSITION", 0, "FIRING"
capture(1000)

# 5) Le Joueur 1 vise la flotte adverse (brouillard, aucun tir encore)
g.phase, g.current, g.message = "FIRING", 0, ""
capture(1300)

# 6) Un tir qui touche -> le Joueur 1 rejoue
hit_one(b1, b1.ships[0], n=1)
g.message = "TOUCHE ! Rejouez !"
capture(1500)

# 7) Un tir sur un navire INTRIQUE : la mesure fige aussi son partenaire
b1._collapse(b1.ships[1])          # <-- vraie mesure (etat de Bell) : les deux figes
hit_one(b1, b1.ships[1], n=1)
g.message = "TOUCHE ! Rejouez ! | Intrication : le navire lie est aussi fige !"
capture(2100)

# 8) Cette fois le Joueur 1 manque -> il passe la main
add_misses(b1, 1)
g.message = "manque. (au tour de l'adversaire)"
capture(1600)

# 9) Transition : c'est au tour du Joueur 2 (on voit bien le changement de main)
g.phase, g.pending_player, g.next_phase = "TRANSITION", 1, "FIRING"
capture(1200)

# 10) Le Joueur 2 tire a son tour et touche
g.phase, g.current = "FIRING", 1
hit_one(b0, b0.ships[0], n=1)
g.message = "TOUCHE ! Rejouez !"
capture(1500)

# 11) Le Joueur 2 manque -> il repasse la main
add_misses(b0, 1)
g.message = "manque. (au tour de l'adversaire)"
capture(1600)

# 12) Transition : retour au Joueur 1
g.phase, g.pending_player, g.next_phase = "TRANSITION", 0, "FIRING"
capture(1200)

# 13) Le Joueur 1 enchaine et coule toute la flotte adverse
g.phase, g.current = "FIRING", 0
sink_everything(b1)
add_misses(b1, 9)                  # de nombreux manques : plateau realiste de fin de partie
g.message = "COULE ! Toute la flotte adverse est detruite."
capture(1800)

# 14) Ecran de victoire (le brouillard montre le plateau reellement crible)
g.phase, g.winner = "GAMEOVER", 0
capture(2400)

# --- assemblage du GIF ------------------------------------------------------
images = [f[0] for f in frames]
durations = [f[1] for f in frames]
images[0].save(
    GIF_PATH,
    save_all=True,
    append_images=images[1:],
    duration=durations,
    loop=0,
    disposal=2,        # chaque frame repart d'un fond propre (pas de trainee)
    optimize=False,    # frames independantes -> rendu fiable partout
)
pygame.quit()
print(f"{GIF_PATH} genere : {len(images)} scenes")
