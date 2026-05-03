# Bittle 👸

Bidule perso pour gérer des recettes, générer une liste de courses, et
calculer les macros par ingrédient à partir du **Fichier canadien des
éléments nutritifs** (CNF, Santé Canada).

## Utilisation

1. Régénérer le site :
   ```sh
   pip install pyyaml          # une seule fois
   python3 build.py
   ```
2. Ouvrir `index.html` dans un navigateur (double-clic).
3. Cocher les recettes voulues, ajuster les portions, cliquer
   « Générer la liste ». La liste est groupée par rayon et fusionne
   les ingrédients identiques quand les unités matchent.

L'état (recettes sélectionnées, items cochés) est sauvegardé dans
`localStorage` du navigateur — il survit aux rechargements.

## Ajouter une recette

Les recettes vivent dans `recipes/<Catégorie>/<slug>.md` et suivent
le format de `recipes/_gabarit.md` :

```markdown
---
titre: ...
portions: 4
temps_prep: 20 min
temps_cuisson: 30 min
tags: [...]
certifie_bittle: false   # passer à true après validation
---

## Ingrédients

### Sous-section optionnelle (sauce, marinade, ...)
- 450 g (1 lb) bifteck de flanc
- 2 gousses d'ail
- 1 oignon

## Préparation
1. Hacher l'ail. Émincer l'oignon.
2. ...

## Notes
- ...
```

**Règle d'or pour les ingrédients** : que la quantité + l'aliment, sans
prep (« haché », « en dés », « émincé »...). La prep va dans les étapes.
La forme/état qui change les macros reste (« désossé sans peau »,
« 35 % M.G. », etc.). Voir l'historique des commits sur la branche
`claude/macro-breakdown-by-ingredient-gi8eW` pour les conventions.

Après modification, relancer `python3 build.py`. Une CI GitHub Actions
le fait automatiquement quand on push sur `main`.

## Calcul des macros

Les macros affichées sont **calculées à partir des ingrédients**, pas
écrites à la main. Le pipeline :

1. `data/ingredients.yml` → mappe chaque alias FR vers un FoodID du CNF
   et un poids par défaut (`count_g`) si l'ingrédient est compté à l'unité.
2. `data/cnf_foods.json` → sous-ensemble du CNF avec valeurs nutritionnelles
   (par 100 g) et facteurs de conversion ml→g.
3. `build.py` → parse chaque ligne d'ingrédient (qty + unit + nom),
   résout le canonique, calcule les grammes, multiplie par les valeurs
   pour 100 g et embarque le résultat dans `recipes.macros_par_ingredient`
   du JSON injecté.
4. `template.html` somme la ventilation, divise par `portions` et affiche
   le résultat dans l'onglet Nutrition.

Pour ajouter un nouvel ingrédient ou un nouvel alias :
1. Trouver son FoodID CNF (chercher dans `data/cnf_foods.json` ou via
   le miroir GitHub `STAT231-S24/CanadianNutrient`).
2. Ajouter l'entrée dans `data/ingredients.yml`.
3. Si nouveau FoodID : régénérer le sous-ensemble CNF avec
   `python3 tools/build_cnf_subset.py` (nécessite les CSV CNF dans
   `/tmp/cnf/`).
4. Rebuild. Le rapport en fin de build indique le % de couverture.

## Catégorisation des ingrédients (liste de courses)

Les ingrédients sont classés par mots-clés vers ces rayons :
Viandes, Produits laitiers & œufs, Fruits & légumes, Conserves,
Pain/pâtes/céréales, Sauces & condiments, Bouillons & vins, Sucré,
Huiles, Épices & herbes séchées, Autres.

Les règles vivent dans `template.html` (constante `CATEGORIES`).
Pour ajouter un cas non géré, éditer le tableau et rebuild.

## Source des données nutritionnelles

[Fichier canadien des éléments nutritifs (CNF), 2015](https://www.canada.ca/fr/sante-canada/services/aliments-nutrition/saine-alimentation/donnees-nutritionnelles.html)
de Santé Canada, via le miroir GitHub
[STAT231-S24/CanadianNutrient](https://github.com/STAT231-S24/CanadianNutrient).
