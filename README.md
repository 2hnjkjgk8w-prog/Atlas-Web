# Atlas Web

Collecteur multi-sources utilisant Python, GitHub Actions et GitHub Pages.

## Installation

1. Créer un dépôt GitHub.
2. Ajouter tous les fichiers en respectant les dossiers.
3. Aller dans Settings > Pages.
4. Choisir Deploy from a branch.
5. Sélectionner la branche main et le dossier / (root).
6. Enregistrer.
7. Aller dans Actions.
8. Lancer le workflow Actualiser Atlas Web.

## Fonctionnalités

- Interface web responsive.
- Recherche dans les informations collectées.
- Tri par date ou par source.
- Récupération de flux RSS et Atom.
- Extraction limitée de pages HTML accessibles.
- Détection des doublons.
- Découverte limitée de liens.
- Mise à jour automatique planifiée.

## Ajouter une source

Modifier data/sources.json.

Exemple de flux RSS :

{
  "name": "Ma source",
  "url": "https://example.com/feed.xml",
  "type": "rss",
  "enabled": true
}

Pour une page HTML, remplacer rss par web.

## Limites

Le collecteur ne peut pas explorer intégralement Internet.
Il ne contourne pas les connexions, les CAPTCHA ou les protections.
Il respecte les restrictions robots.txt pour les pages HTML.
Les pages nécessitant JavaScript ne sont pas prises en charge par cette version.

Les conditions d'utilisation et les quotas des services s'appliquent.
GitHub Actions peut retarder les exécutions planifiées.
