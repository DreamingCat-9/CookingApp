# Gestion alimentaire

Bidule perso pour générer une liste de courses à partir des recettes
markdown stockées dans `recipes/`.

## Utilisation

1. Régénérer le site :
   ```sh
   python3 build.py
   ```
2. Ouvrir `index.html` dans un navigateur (double-clic).
3. Cocher les recettes voulues, ajuster les portions, cliquer
   « Générer la liste ». La liste est groupée par rayon et fusionne
   les ingrédients identiques quand les unités matchent.

L'état (recettes sélectionnées, items cochés) est sauvegardé dans
`localStorage` du navigateur — il survit aux rechargements.

## Ajouter / modifier une recette

Les recettes vivent dans `recipes/<Catégorie>/<slug>.md` et suivent
le format de `recipes/_gabarit.md` :

```markdown
---
titre: ...
portions: 4
temps_prep: 20 min
temps_cuisson: 30 min
tags: [...]
derniere_fois: 
---

## Ingrédients

### Sous-section optionnelle (sauce, marinade, ...)
- 450 g (1 lb) ingrédient
- 2 gousses d'ail hachées
- ...

## Préparation
1. ...

## Notes
- ...
```

Après modification, relancer `python3 build.py` pour régénérer
`index.html`.

## Catégorisation

Les ingrédients sont classés par mots-clés vers ces rayons :
Viandes, Produits laitiers & œufs, Fruits & légumes, Conserves,
Pain/pâtes/céréales, Sauces & condiments, Bouillons & vins, Sucré,
Huiles, Épices & herbes séchées, Autres.

Les règles vivent dans `template.html` (constante `CATEGORIES`).
Pour ajouter un cas non géré, éditer le tableau et rebuild.
