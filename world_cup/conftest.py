# Rend le paquet src/ de world_cup importable quand pytest est lance depuis ce dossier.
# Ce sous-projet a son propre src/ : lancer sa suite avec `cd world_cup && python -m pytest`,
# jamais depuis la racine du depot, ou les deux src/ entreraient en collision.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
