# Permet a pytest d importer le package src depuis la racine du depot.
# world_cup/ est un sous-projet autonome avec son propre src/ : sa suite se lance
# separement (`cd world_cup && python -m pytest`), sinon les deux src/ se marchent dessus.
collect_ignore_glob = ["world_cup/*"]
