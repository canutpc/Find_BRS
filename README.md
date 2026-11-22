# 🏙️ Veille Immobilière — Lyon Croix-Rousse (BRS & Programmes Neufs)

Automatisation quotidienne (via **GitHub Actions** et **GitHub Pages**) permettant de surveiller les nouvelles sorties en **Bail Réel Solidaire (BRS)** et les **projets de construction neufs** à venir sur le secteur strict de **Lyon Croix-Rousse**.

---

## 🎯 Critères de recherche

* **Périmètre inclus :** Lyon 4e (Plateau de la Croix-Rousse) et Lyon 1er (Pentes de la Croix-Rousse) — codes postaux `69004` et `69001`.
* **Périmètre strictement exclu :** Caluire-et-Cuire, Saint-Clair, Montessuy, Cuire et tout autre arrondissement/commune limitrophe.
* **Typologie :** Appartement **T4** (3 chambres).
* **Budget cible :** Environ **300 000 €**.
* **Dispositifs :** BRS (Bail Réel Solidaire), accession sociale encadrée et nouveaux lancements neufs.

---

## 🗂️ Structure du dépôt

```text
.
├── .github/
│   └── workflows/
│       └── veille.yml      # Planification quotidienne (GitHub Actions)
├── index.html              # Tableau de bord web (GitHub Pages)
├── scraper.py              # Script Python de collecte et de filtrage strict
├── data.json               # Généré automatiquement à chaque exécution
└── README.md               # Documentation du projet
