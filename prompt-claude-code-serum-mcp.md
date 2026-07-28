# Comment utiliser ce document

Copiez-collez tout ce qui suit le séparateur `---` directement dans Claude Code (nouvelle session, à la racine d'un dossier vide ou d'un nouveau dépôt Git). C'est rédigé pour être auto-suffisant : Claude Code y trouvera le contexte, les contraintes techniques vérifiées, l'architecture cible et les liens vers toutes les ressources externes nécessaires.

---

## Rôle et mission

Tu es chargé de développer, de A à Z et en public sur GitHub, un outil open source qui permet de **générer, modifier et sauvegarder des presets pour le synthétiseur Xfer Serum 2, à partir d'une simple description textuelle** (ex : "crée un lead Future Bass agressif", "un pad sombre et évolutif avec du chorus", "rends ce son plus warm et moins agressif").

Ce projet doit être pensé comme un **serveur MCP (Model Context Protocol)** utilisable par Claude Code (et par n'importe quel client MCP), pas comme une application autonome avec interface graphique.

**Objectif produit final** : depuis Claude Code (ou un autre client MCP), un utilisateur écrit "génère-moi une basse acide façon TB-303" et obtient un vrai fichier `.SerumPreset` valide, déposé dans son dossier de presets Serum, qu'il peut immédiatement charger dans le plugin — peu importe le DAW utilisé (mon usage personnel est FL Studio 21, mais l'outil ne doit dépendre d'aucun DAW en particulier).

## Ce que ce projet N'EST PAS (hors périmètre explicite)

Ces exclusions sont volontaires et importantes, ne les réintroduis pas sans qu'on en discute :

- **Pas de génération ou d'écriture de MIDI.**
- **Pas de pilotage temps réel d'un DAW** (pas d'automation, pas de contrôle de plugin en live, pas de MIDI scripting FL Studio, pas de Remote Script Ableton, pas de ReaScript).
- **Pas de chargement du plugin Serum lui-même** dans le pipeline de génération — on ne rend pas d'audio, on ne prévisualise pas le son en V1.
- Le DAW (FL Studio 21 dans mon cas) n'intervient **à aucun moment** dans le pipeline technique. C'est uniquement l'endroit où j'ouvrirai Serum après coup pour utiliser le preset généré.

Le cœur du projet est donc : **texte en entrée → fichier `.SerumPreset` valide en sortie.** Rien de plus en V1.

## Contexte technique vérifié (ne pas re-découvrir, partir de là)

### Absence d'API officielle
Xfer Records (éditeur de Serum) ne publie aucun SDK ni documentation développeur. Le format de preset Serum 2 (`.SerumPreset`) n'est pas documenté officiellement. Steve Duda (créateur de Serum) a évoqué dans un podcast en 2025 vouloir un jour l'ouvrir, mais ce n'est pas d'actualité — nous devons nous appuyer sur le travail de reverse engineering déjà fait par la communauté.

### Le format a déjà été percé par la communauté (avril 2025)
Le format `.SerumPreset` est du **JSON compressé**. Un outil CLI Python le décode/encode déjà intégralement :

- **Bibliothèque de référence à utiliser (ou dont s'inspirer fortement) :** `https://github.com/KennethWussmann/serum-preset-packager`
  Permet de faire `unpack` (`.SerumPreset` → JSON lisible) et `pack` (JSON → `.SerumPreset` valide). Gère aussi `.XferArpBank`. Ne gère PAS le format legacy `.fxp` (Serum 1) — ce n'est pas grave, on cible uniquement Serum 2.
- **Portage TypeScript équivalent, si tu préfères un stack Node :** `https://github.com/CharlesBT/node-serum2-preset-packager`
- Notes de reverse engineering détaillées (utile si tu dois déboguer ou étendre le format) : `https://gist.github.com/0xdevalias/135a18e979ac8e302ebbc700a50a8d74` et `https://gist.github.com/0xdevalias/5a06349b376d01b2a76ad27a86b08c1b`

**Action attendue de toi en tout début de projet** : cloner/étudier `serum-preset-packager`, l'utiliser (via appel de sous-processus Python, ou réimplémentation propre si sa licence/qualité de code le justifie) pour comprendre la structure exacte du JSON décompressé sur un vrai preset d'exemple.

### Schéma des paramètres Serum
Une table quasi complète des paramètres du moteur de synthèse (noms, min/max, type d'affichage, unité, valeur par défaut — environ 289 paramètres : oscillateurs A/B/Noise/Sub, filtre, 3 enveloppes, 8 LFOs, matrice de modulation 32 slots, et tous les effets : reverb, distortion, flanger, phaser, chorus, delay, compresseur, EQ, hyper/unison) est documentée ici, extraite du fichier interne `SYParameters.txt` :

- `https://gist.github.com/0xdevalias/135a18e979ac8e302ebbc700a50a8d74` (fichiers `serum-params-SYParameters-1.334.txt` et `serum-params-from-pedalboard.txt` dans ce gist)
- Dump JSON des paramètres VST3 d'une instance Serum 2 fraîchement chargée : `https://gist.github.com/KennethWussmann/5b58e4de728680a0bf8906a8b113103d`

**Important** : cette table date de Serum 1 dans sa nomenclature d'origine ; Serum 2 a ajouté des fonctionnalités (oscillateur granulaire, échantillonneur, arpégiateur/séquenceur, nouveaux types d'oscillateurs). **Ta première tâche technique doit être de croiser cette table avec la structure JSON réelle obtenue via `serum-preset-packager` sur un export Serum 2 récent**, pour produire un schéma à jour et fiable — ne te contente pas de la table Serum 1 telle quelle.

### Emplacement du dossier de presets
Le dossier utilisateur Serum est déplaçable et se retrouve via le menu du plugin ("Show Serum Presets folder"). Emplacement typique par défaut sous Windows : `Documents\Xfer\Serum Presets\Presets\User\` (peut varier selon l'installation). **Ne code jamais ce chemin en dur** : rends-le configurable (variable d'environnement `SERUM_PRESETS_PATH` ou fichier de config), avec une détection automatique en fallback si possible, et un message clair si le chemin n'est pas trouvé/configuré.

### Concurrence et différenciation à connaître
Il existe déjà des projets/produits similaires (à ne pas copier, mais à connaître pour se différencier honnêtement dans le README) :
- `https://github.com/Tdub206/Serum-Preset-Generator` (API Python, génération depuis JSON de config)
- `https://github.com/potatoTeto/SerumPresetGenerator` (bibliothèque C#, clean-room)
- Pounding Systems propose un générateur de presets Serum par IA en SaaS payant (`https://pounding.systems/products/ai-serum-preset-generator`)

**Notre différenciation** : outil open source, natif MCP/Claude Code (pas une appli web séparée), édition conversationnelle itérative d'un preset existant (pas seulement génération one-shot), transparence totale du mapping paramètres.

## Architecture cible

```
Prompt utilisateur (langage naturel)
        │
        ▼
Serveur MCP (Python recommandé, SDK officiel `mcp`)
        │
        ├── Tool: generate_preset(description: str) -> preset_path
        ├── Tool: edit_preset(preset_path: str, instruction: str) -> preset_path
        ├── Tool: list_parameters() -> schéma complet (pour que Claude Code puisse
        │         consulter les paramètres disponibles avant de proposer une édition)
        └── Tool: describe_preset(preset_path: str) -> résumé lisible du preset
                  (utile pour que l'utilisateur comprenne ce qui a été généré)
        │
        ▼
Moteur de génération :
  1. Le LLM (appelé via l'API Claude, avec le schéma de paramètres en contexte)
     traduit la description en une structure de paramètres cible, au format JSON
     STRICTEMENT contraint par le schéma (bornes min/max respectées, unités correctes)
  2. Cette structure est fusionnée sur un preset "init" de base (fourni en fixture)
  3. `serum-preset-packager` (ou équivalent) transforme ce JSON en `.SerumPreset` valide
        │
        ▼
Écriture du fichier dans le dossier presets utilisateur configuré
```

## Stack technique recommandée

- **Langage** : Python 3.11+ (écosystème le plus mature pour ce type de projet, et compatible avec `serum-preset-packager`).
- **SDK MCP** : le SDK Python officiel du Model Context Protocol (`mcp`, cf. `https://modelcontextprotocol.io` pour la doc à jour — vérifie la documentation actuelle avant de coder, elle évolue).
- **Appel LLM** : l'API Anthropic (`anthropic` Python SDK), avec function calling / structured output contraint par un schéma JSON strict représentant les paramètres Serum valides — pas de génération libre non validée.
- **Tests** : `pytest`, avec des tests de non-régression sur le round-trip `pack(unpack(preset)) == preset` pour détecter toute rupture de compatibilité avec de futures versions de Serum.
- **Gestion de dépendances** : `uv` ou `poetry` (choisis celui qui te semble le plus adapté à un projet open source moderne en 2026).

## Structure de dépôt attendue

```
serum-mcp/
├── README.md                     # voir section "Exigences README" ci-dessous
├── LICENSE                       # MIT recommandé, sauf contre-indication que tu identifierais
├── CONTRIBUTING.md
├── pyproject.toml
├── src/
│   └── serum_mcp/
│       ├── server.py             # point d'entrée du serveur MCP
│       ├── tools/                # implémentation des tools MCP listés ci-dessus
│       ├── preset/
│       │   ├── packer.py         # wrapper autour de serum-preset-packager (ou réimplémentation)
│       │   ├── schema.py         # schéma des paramètres Serum (issu de la recherche croisée)
│       │   └── validator.py      # validation des bornes/unités avant écriture
│       ├── generation/
│       │   └── llm_mapper.py     # prompt engineering + appel LLM contraint par schéma
│       └── config.py             # gestion du chemin du dossier presets, etc.
├── fixtures/
│   └── init_preset.SerumPreset   # preset de base servant de point de départ aux générations
├── tests/
└── docs/
    └── PARAMETER_SCHEMA.md       # documentation lisible du schéma de paramètres
```

## Exigences pour un projet open source de qualité (le "faire pour la communauté")

Comme ce projet est fait pour être public, obtenir de la visibilité et être utile à d'autres, respecte ces standards dès le premier commit :

1. **README.md en anglais** (l'audience GitHub est majoritairement anglophone — même si tu me parles en français dans nos échanges, tout le contenu du dépôt doit être en anglais), avec :
   - Une accroche claire en une phrase (ce que fait l'outil, pour qui).
   - Un exemple concret immédiat (avant/après : prompt → fichier généré).
   - Instructions d'installation et de configuration MCP pour Claude Code / Claude Desktop.
   - Une section "How it works" qui explique honnêtement l'architecture (transparence = crédibilité).
   - Une section "Disclaimer" claire : projet non affilié à Xfer Records, basé sur un format reverse-engineered par la communauté, susceptible de casser à chaque mise à jour majeure de Serum.
   - Des badges (licence, build status si CI, version Python).
2. **Licence MIT** par défaut (vérifie la compatibilité avec les dépendances utilisées, notamment `serum-preset-packager`, avant de trancher).
3. **CI GitHub Actions** minimale : lint + tests à chaque PR.
4. **CONTRIBUTING.md** invitant explicitement les contributions (mapping de paramètres manquants, support d'autres synthés Xfer, etc.).
5. **Topics GitHub** pertinents à suggérer : `mcp`, `model-context-protocol`, `claude-code`, `serum`, `synthesizer`, `music-production`, `ai-music`, `sound-design`.
6. **Nom de projet : `serum-mcp`** (déjà décidé, ne pas en proposer d'autre). Utilise ce nom pour le dossier racine, le nom du package Python (`serum_mcp` en snake_case pour le module), le titre du README et, si tu initialises un dépôt distant, comme nom de repo GitHub.

## Roadmap

- **V1 (périmètre de cette session)** : génération depuis description libre, édition incrémentale d'un preset existant par instruction, export direct dans le dossier presets utilisateur, schéma de paramètres documenté et testé.
- **V2 (à ne pas commencer maintenant, juste à garder en tête dans l'architecture)** : mode "reproduis ce son" à partir d'un fichier audio, ce qui nécessitera d'intégrer un rendu audio (ex. `spotify/pedalboard`) et une boucle de comparaison spectrale — ne sur-architecture pas la V1 pour ça, mais évite les choix qui rendraient ça impossible plus tard.

## Ta première session de travail — livrables attendus

1. Clone et étudie `serum-preset-packager`, produis un JSON décompressé d'un vrai preset Serum 2 (utilise un preset factory si tu n'en as pas d'autre sous la main, ou demande-m'en un si nécessaire) pour valider ta compréhension du format réel.
2. Construis et documente le schéma de paramètres à jour (croisement table Serum 1 + structure JSON réelle Serum 2), dans `docs/PARAMETER_SCHEMA.md` et `src/serum_mcp/preset/schema.py`.
3. Mets en place la structure de dépôt ci-dessus avec un `generate_preset` fonctionnel de bout en bout sur un cas simple (ex. "basse simple avec filtre passe-bas").
4. Initialise le dépôt Git (nom `serum-mcp`) avec un premier commit propre, et rédige le README selon les exigences ci-dessus.
5. Résume-moi à la fin ce qui fonctionne, ce qui reste incertain (notamment tout paramètre du schéma que tu n'aurais pas pu valider avec certitude), et les prochaines étapes proposées.

N'hésite pas à me poser des questions si un point de ce brief est ambigu — mieux vaut clarifier maintenant qu'implémenter dans la mauvaise direction.
