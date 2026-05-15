# RAPPORT — TP2 : MongoDB — Plateforme de Gestion de Dossiers Médicaux
### HealthCare DZ | Module : Bases de Données Avancées

---

## Table des Matières
1. [Justification du Schéma : Embedding vs Referencing](#1-justification-du-schéma)
2. [Ex1 — Modélisation et Insertion](#2-ex1--modélisation-et-insertion)
3. [Ex2 — Requêtes de Base](#3-ex2--requêtes-de-base)
4. [Ex3 — Agrégation Avancée](#4-ex3--agrégation-avancée)
5. [Ex4 — Index et Optimisation](#5-ex4--index-et-optimisation)
6. [Ex5 — $lookup et Données Référencées](#6-ex5--lookup-et-données-référencées)
7. [Bonus — Transactions Multi-documents](#7-bonus--transactions-multi-documents)
8. [Synthèse et Conclusions](#8-synthèse-et-conclusions)

---

## 1. Justification du Schéma

### 1.1 Principe de décision : Embedding vs Referencing

La règle fondamentale en MongoDB est :

> **"Store together what you access together"**

On choisit entre les deux approches selon trois critères :

| Critère | Embedding | Referencing |
|---------|-----------|-------------|
| Fréquence d'accès conjoint | Élevée | Faible |
| Taille des sous-documents | Petite / bornée | Grande / illimitée |
| Mise à jour indépendante | Rare | Fréquente |

---

### 1.2 Décisions pour HealthCare DZ

#### ✅ Consultations → **EMBEDDED** dans `patients`

**Justification :**
- Chaque affichage du dossier patient nécessite **systématiquement** les consultations → un seul accès DB
- Le nombre de consultations est **borné dans le temps** (quelques dizaines par an au maximum)
- La limite MongoDB de 16 Mo par document n'est pas atteinte pour une vie de consultations médicales
- Les consultations n'ont **aucun sens sans leur patient** (pas de lecture indépendante)
- Évite les JOINs coûteux (`$lookup`) pour le cas d'usage principal

```
Accès dossier patient SANS embedding : 1 requête patients + 1 requête consultations = 2 aller-retours
Accès dossier patient AVEC embedding : 1 seule requête                              = 1 aller-retour
```

#### ✅ Analyses → **REFERENCED** dans une collection séparée

**Justification :**
- Les résultats d'analyses (NFS, glycémie, lipidogramme, ECG) ont des structures **très hétérogènes** → schéma flexible nécessaire
- Le volume peut devenir **très grand** (images ECG encodées, centaines d'analyses sur 30 ans)
- Les analyses sont souvent consultées **indépendamment** par le laboratoire, sans lire tout le dossier
- Les analyses peuvent être **validées / mises à jour** sans toucher au document patient
- Permet des requêtes statistiques lourdes sur la collection `analyses` **sans charger les patients**

```
Modèle relationnel équivalent : 12 tables + JOINs
Modèle MongoDB choisi         : 2 collections + $lookup uniquement quand nécessaire
```

#### Schéma final adopté

```
Collection : patients          Collection : analyses
┌─────────────────────┐       ┌──────────────────────────┐
│ _id                 │◄──┐   │ _id                      │
│ cin                 │   │   │ patient_id  ──────────────┘
│ nom, prenom         │   │   │ date                     │
│ dateNaissance       │   │   │ type                     │
│ sexe                │   │   │ resultats (flexible)     │
│ adresse             │   │   │ laboratoire              │
│ groupeSanguin       │   │   │ valide                   │
│ antecedents[]       │   │   └──────────────────────────┘
│ allergies[]         │   │
│ consultations[] ←─EMBEDDED  │
│   ├ date            │   │
│   ├ medecin{}       │   │
│   ├ diagnostic      │   │
│   ├ tension{}       │   │
│   └ medicaments[]   │   │
│ analyses[]          │   │
│   └ analyse_id ─────────┘
└─────────────────────┘
```

---

## 2. Ex1 — Modélisation et Insertion

### 2.1 Création de la collection avec validation de schéma

```javascript
// ex1_modelisation.js — Partie 1 : Validation de schéma

db.createCollection("patients", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["cin", "nom", "prenom", "dateNaissance", "sexe", "adresse", "groupeSanguin"],
      properties: {
        cin: {
          bsonType: "string",
          pattern: "^[0-9]{12}$",
          description: "Numéro national algérien — 12 chiffres obligatoires"
        },
        nom: {
          bsonType: "string",
          minLength: 2,
          maxLength: 50,
          description: "Nom de famille obligatoire"
        },
        prenom: {
          bsonType: "string",
          minLength: 2,
          maxLength: 50,
          description: "Prénom obligatoire"
        },
        dateNaissance: {
          bsonType: "date",
          description: "Date de naissance au format ISODate"
        },
        sexe: {
          bsonType: "string",
          enum: ["M", "F"],
          description: "Sexe : M ou F uniquement"
        },
        adresse: {
          bsonType: "object",
          required: ["wilaya"],
          properties: {
            wilaya: { bsonType: "string" },
            commune: { bsonType: "string" }
          }
        },
        groupeSanguin: {
          bsonType: "string",
          enum: ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"],
          description: "Groupe sanguin valide"
        },
        antecedents: {
          bsonType: "array",
          items: { bsonType: "string" }
        },
        allergies: {
          bsonType: "array",
          items: { bsonType: "string" }
        },
        consultations: {
          bsonType: "array",
          items: {
            bsonType: "object",
            required: ["date", "medecin", "diagnostic"],
            properties: {
              date: { bsonType: "date" },
              medecin: {
                bsonType: "object",
                required: ["nom", "specialite"],
                properties: {
                  nom: { bsonType: "string" },
                  specialite: { bsonType: "string" }
                }
              },
              diagnostic: { bsonType: "string" },
              tension: {
                bsonType: "object",
                properties: {
                  systolique: { bsonType: "int" },
                  diastolique: { bsonType: "int" }
                }
              },
              medicaments: {
                bsonType: "array",
                items: {
                  bsonType: "object",
                  properties: {
                    nom: { bsonType: "string" },
                    dosage: { bsonType: "string" },
                    duree: { bsonType: "string" }
                  }
                }
              }
            }
          }
        }
      }
    }
  },
  validationAction: "error",
  validationLevel: "moderate"
});
```

### 2.2 Insertion de 20 patients algériens réalistes

```javascript
// ex1_modelisation.js — Partie 2 : Insertion des patients

db.patients.insertMany([
  {
    cin: "198701032101",
    nom: "Bensalem",
    prenom: "Ahmed",
    dateNaissance: new Date("1987-01-03"),
    sexe: "M",
    adresse: { wilaya: "Alger", commune: "Bab Ezzouar" },
    groupeSanguin: "O+",
    antecedents: ["Diabète type 2", "HTA"],
    allergies: ["Pénicilline"],
    consultations: [
      {
        id: UUID(),
        date: new Date("2024-01-15"),
        medecin: { nom: "Dr. Mansouri", specialite: "Cardiologie" },
        diagnostic: "Hypertension artérielle",
        tension: { systolique: 145, diastolique: 92 },
        medicaments: [
          { nom: "Amlodipine", dosage: "5mg", duree: "30 jours" },
          { nom: "Ramipril", dosage: "10mg", duree: "30 jours" }
        ],
        notes: "Surveillance tensionnelle recommandée, régime pauvre en sel"
      },
      {
        id: UUID(),
        date: new Date("2024-03-20"),
        medecin: { nom: "Dr. Mansouri", specialite: "Cardiologie" },
        diagnostic: "HTA contrôlée",
        tension: { systolique: 132, diastolique: 84 },
        medicaments: [
          { nom: "Amlodipine", dosage: "5mg", duree: "60 jours" }
        ],
        notes: "Amélioration notable"
      },
      {
        id: UUID(),
        date: new Date("2024-06-10"),
        medecin: { nom: "Dr. Khelifi", specialite: "Endocrinologie" },
        diagnostic: "Diabète type 2 déséquilibré",
        tension: { systolique: 138, diastolique: 88 },
        medicaments: [
          { nom: "Metformine", dosage: "1000mg", duree: "90 jours" },
          { nom: "Glibenclamide", dosage: "5mg", duree: "90 jours" }
        ],
        notes: "HbA1c à 8.2% - renforcer le traitement"
      }
    ],
    analyses: []
  },
  {
    cin: "199205154202",
    nom: "Hadj Aissa",
    prenom: "Fatima",
    dateNaissance: new Date("1992-05-15"),
    sexe: "F",
    adresse: { wilaya: "Oran", commune: "Bir El Djir" },
    groupeSanguin: "A+",
    antecedents: [],
    allergies: ["Aspirine"],
    consultations: [
      {
        id: UUID(),
        date: new Date("2024-02-08"),
        medecin: { nom: "Dr. Benali", specialite: "Gynécologie" },
        diagnostic: "Anémie ferriprive",
        tension: { systolique: 110, diastolique: 70 },
        medicaments: [
          { nom: "Tardyferon", dosage: "80mg", duree: "60 jours" }
        ],
        notes: "Supplémentation en fer nécessaire"
      },
      {
        id: UUID(),
        date: new Date("2024-04-22"),
        medecin: { nom: "Dr. Benali", specialite: "Gynécologie" },
        diagnostic: "Anémie en rémission",
        tension: { systolique: 115, diastolique: 72 },
        medicaments: [],
        notes: "Hémoglobine normalisée"
      }
    ],
    analyses: []
  },
  {
    cin: "196308091503",
    nom: "Meziane",
    prenom: "Mohamed Lamine",
    dateNaissance: new Date("1963-08-09"),
    sexe: "M",
    adresse: { wilaya: "Alger", commune: "Hussein Dey" },
    groupeSanguin: "B+",
    antecedents: ["Diabète type 2", "HTA", "Insuffisance rénale chronique"],
    allergies: ["Pénicilline", "Sulfamides"],
    consultations: [
      {
        id: UUID(),
        date: new Date("2024-01-05"),
        medecin: { nom: "Dr. Saadi", specialite: "Néphrologie" },
        diagnostic: "Insuffisance rénale chronique stade 3",
        tension: { systolique: 158, diastolique: 98 },
        medicaments: [
          { nom: "Losartan", dosage: "50mg", duree: "30 jours" },
          { nom: "Furosémide", dosage: "40mg", duree: "30 jours" }
        ],
        notes: "Créatinine à 180 µmol/L - régime hypoprotidique"
      },
      {
        id: UUID(),
        date: new Date("2024-03-12"),
        medecin: { nom: "Dr. Saadi", specialite: "Néphrologie" },
        diagnostic: "Insuffisance rénale chronique stade 3 stable",
        tension: { systolique: 148, diastolique: 91 },
        medicaments: [
          { nom: "Losartan", dosage: "100mg", duree: "60 jours" }
        ],
        notes: "Stabilisation - surveillance bimestrielle"
      },
      {
        id: UUID(),
        date: new Date("2024-05-20"),
        medecin: { nom: "Dr. Khelifi", specialite: "Endocrinologie" },
        diagnostic: "Diabète type 2 avec complications",
        tension: { systolique: 152, diastolique: 94 },
        medicaments: [
          { nom: "Insuline Glargine", dosage: "20UI", duree: "30 jours" }
        ],
        notes: "Passage à l'insuline - HbA1c à 9.1%"
      }
    ],
    analyses: []
  },
  {
    cin: "197512254304",
    nom: "Boudjema",
    prenom: "Karima",
    dateNaissance: new Date("1975-12-25"),
    sexe: "F",
    adresse: { wilaya: "Constantine", commune: "El Khroub" },
    groupeSanguin: "AB+",
    antecedents: ["Asthme"],
    allergies: [],
    consultations: [
      {
        id: UUID(),
        date: new Date("2024-01-30"),
        medecin: { nom: "Dr. Ferhat", specialite: "Pneumologie" },
        diagnostic: "Asthme modéré persistant",
        tension: { systolique: 120, diastolique: 78 },
        medicaments: [
          { nom: "Salbutamol", dosage: "100µg", duree: "À la demande" },
          { nom: "Béclométasone", dosage: "250µg", duree: "90 jours" }
        ],
        notes: "Contrôle asthmatique insuffisant - ajouter corticoïde inhalé"
      }
    ],
    analyses: []
  },
  {
    cin: "198903185105",
    nom: "Djellali",
    prenom: "Sofiane",
    dateNaissance: new Date("1989-03-18"),
    sexe: "M",
    adresse: { wilaya: "Sétif", commune: "Sétif" },
    groupeSanguin: "O-",
    antecedents: [],
    allergies: [],
    consultations: [
      {
        id: UUID(),
        date: new Date("2024-02-14"),
        medecin: { nom: "Dr. Merbah", specialite: "Médecine générale" },
        diagnostic: "Grippe saisonnière",
        tension: { systolique: 118, diastolique: 75 },
        medicaments: [
          { nom: "Paracétamol", dosage: "1g", duree: "5 jours" },
          { nom: "Ibuprofène", dosage: "400mg", duree: "3 jours" }
        ],
        notes: "Repos recommandé, hydratation"
      },
      {
        id: UUID(),
        date: new Date("2024-07-03"),
        medecin: { nom: "Dr. Merbah", specialite: "Médecine générale" },
        diagnostic: "Gastro-entérite aiguë",
        tension: { systolique: 115, diastolique: 72 },
        medicaments: [
          { nom: "Smecta", dosage: "3g", duree: "5 jours" }
        ],
        notes: "Régime sans résidus"
      }
    ],
    analyses: []
  },
  {
    cin: "195601072106",
    nom: "Chaoui",
    prenom: "Abdelkader",
    dateNaissance: new Date("1956-01-07"),
    sexe: "M",
    adresse: { wilaya: "Alger", commune: "Kouba" },
    groupeSanguin: "A-",
    antecedents: ["HTA", "Coronaropathie"],
    allergies: ["Pénicilline"],
    consultations: [
      {
        id: UUID(),
        date: new Date("2024-01-10"),
        medecin: { nom: "Dr. Mansouri", specialite: "Cardiologie" },
        diagnostic: "Angor stable",
        tension: { systolique: 142, diastolique: 88 },
        medicaments: [
          { nom: "Aspirine", dosage: "75mg", duree: "Longue durée" },
          { nom: "Atorvastatine", dosage: "40mg", duree: "Longue durée" },
          { nom: "Bisoprolol", dosage: "5mg", duree: "30 jours" }
        ],
        notes: "ECG dans les normes - coronarographie à programmer"
      },
      {
        id: UUID(),
        date: new Date("2024-04-05"),
        medecin: { nom: "Dr. Mansouri", specialite: "Cardiologie" },
        diagnostic: "Angor stable contrôlé",
        tension: { systolique: 135, diastolique: 84 },
        medicaments: [
          { nom: "Aspirine", dosage: "75mg", duree: "Longue durée" },
          { nom: "Bisoprolol", dosage: "10mg", duree: "60 jours" }
        ],
        notes: "Stabilisation - effort toléré"
      },
      {
        id: UUID(),
        date: new Date("2024-08-19"),
        medecin: { nom: "Dr. Mansouri", specialite: "Cardiologie" },
        diagnostic: "HTA + Coronaropathie suivis",
        tension: { systolique: 138, diastolique: 86 },
        medicaments: [
          { nom: "Ramipril", dosage: "5mg", duree: "90 jours" }
        ],
        notes: "Bonne observance thérapeutique"
      }
    ],
    analyses: []
  },
  {
    cin: "200110093207",
    nom: "Aoudia",
    prenom: "Yasmine",
    dateNaissance: new Date("2001-10-09"),
    sexe: "F",
    adresse: { wilaya: "Tizi Ouzou", commune: "Tizi Ouzou" },
    groupeSanguin: "B-",
    antecedents: [],
    allergies: [],
    consultations: [
      {
        id: UUID(),
        date: new Date("2024-03-01"),
        medecin: { nom: "Dr. Amrani", specialite: "Dermatologie" },
        diagnostic: "Acné vulgaire modérée",
        tension: { systolique: 112, diastolique: 70 },
        medicaments: [
          { nom: "Doxycycline", dosage: "100mg", duree: "90 jours" },
          { nom: "Peroxyde de benzoyle", dosage: "5%", duree: "90 jours" }
        ],
        notes: "Éviter exposition solaire"
      }
    ],
    analyses: []
  },
  {
    cin: "197004116108",
    nom: "Kaddour",
    prenom: "Rachid",
    dateNaissance: new Date("1970-04-11"),
    sexe: "M",
    adresse: { wilaya: "Annaba", commune: "Sidi Amar" },
    groupeSanguin: "O+",
    antecedents: ["Diabète type 2"],
    allergies: [],
    consultations: [
      {
        id: UUID(),
        date: new Date("2024-01-22"),
        medecin: { nom: "Dr. Khelifi", specialite: "Endocrinologie" },
        diagnostic: "Diabète type 2 équilibré",
        tension: { systolique: 125, diastolique: 80 },
        medicaments: [
          { nom: "Metformine", dosage: "850mg", duree: "90 jours" }
        ],
        notes: "HbA1c à 6.8% - bon contrôle glycémique"
      },
      {
        id: UUID(),
        date: new Date("2024-05-15"),
        medecin: { nom: "Dr. Khelifi", specialite: "Endocrinologie" },
        diagnostic: "Diabète type 2 équilibré",
        tension: { systolique: 128, diastolique: 82 },
        medicaments: [
          { nom: "Metformine", dosage: "850mg", duree: "90 jours" }
        ],
        notes: "Continuer le traitement - HbA1c à 7.0%"
      },
      {
        id: UUID(),
        date: new Date("2024-09-08"),
        medecin: { nom: "Dr. Merbah", specialite: "Médecine générale" },
        diagnostic: "Rhinite allergique",
        tension: { systolique: 122, diastolique: 78 },
        medicaments: [
          { nom: "Loratadine", dosage: "10mg", duree: "30 jours" }
        ],
        notes: "Éviction des allergènes"
      }
    ],
    analyses: []
  },
  {
    cin: "198506227309",
    nom: "Brahimi",
    prenom: "Nadia",
    dateNaissance: new Date("1985-06-22"),
    sexe: "F",
    adresse: { wilaya: "Blida", commune: "Boufarik" },
    groupeSanguin: "AB-",
    antecedents: ["HTA"],
    allergies: ["Ibuprofène"],
    consultations: [
      {
        id: UUID(),
        date: new Date("2024-02-28"),
        medecin: { nom: "Dr. Mansouri", specialite: "Cardiologie" },
        diagnostic: "Hypertension artérielle grade 2",
        tension: { systolique: 162, diastolique: 102 },
        medicaments: [
          { nom: "Perindopril", dosage: "8mg", duree: "30 jours" },
          { nom: "Amlodipine", dosage: "10mg", duree: "30 jours" }
        ],
        notes: "Tension très élevée - bithérapie initiée"
      },
      {
        id: UUID(),
        date: new Date("2024-04-15"),
        medecin: { nom: "Dr. Mansouri", specialite: "Cardiologie" },
        diagnostic: "HTA grade 2 en cours de contrôle",
        tension: { systolique: 148, diastolique: 94 },
        medicaments: [
          { nom: "Perindopril", dosage: "8mg", duree: "60 jours" },
          { nom: "Amlodipine", dosage: "10mg", duree: "60 jours" }
        ],
        notes: "Amélioration progressive"
      },
      {
        id: UUID(),
        date: new Date("2024-07-20"),
        medecin: { nom: "Dr. Mansouri", specialite: "Cardiologie" },
        diagnostic: "HTA contrôlée",
        tension: { systolique: 135, diastolique: 86 },
        medicaments: [
          { nom: "Perindopril", dosage: "4mg", duree: "90 jours" }
        ],
        notes: "Réduction de dose - maintenir l'effort physique"
      }
    ],
    analyses: []
  },
  {
    cin: "196111308210",
    nom: "Hamidi",
    prenom: "Fatima Zohra",
    dateNaissance: new Date("1961-11-30"),
    sexe: "F",
    adresse: { wilaya: "Alger", commune: "Dar El Beida" },
    groupeSanguin: "A+",
    antecedents: ["Diabète type 2", "HTA", "Dyslipidémie"],
    allergies: ["Pénicilline"],
    consultations: [
      {
        id: UUID(),
        date: new Date("2024-01-08"),
        medecin: { nom: "Dr. Khelifi", specialite: "Endocrinologie" },
        diagnostic: "Diabète type 2 + HTA + Dyslipidémie",
        tension: { systolique: 155, diastolique: 96 },
        medicaments: [
          { nom: "Metformine", dosage: "1000mg", duree: "90 jours" },
          { nom: "Amlodipine", dosage: "5mg", duree: "90 jours" },
          { nom: "Atorvastatine", dosage: "20mg", duree: "90 jours" }
        ],
        notes: "Syndrome métabolique - prise en charge globale"
      },
      {
        id: UUID(),
        date: new Date("2024-04-02"),
        medecin: { nom: "Dr. Khelifi", specialite: "Endocrinologie" },
        diagnostic: "Syndrome métabolique en cours de traitement",
        tension: { systolique: 142, diastolique: 90 },
        medicaments: [
          { nom: "Metformine", dosage: "1000mg", duree: "90 jours" },
          { nom: "Amlodipine", dosage: "10mg", duree: "90 jours" }
        ],
        notes: "LDL à 1.8g/L - objectif atteint"
      }
    ],
    analyses: []
  },
  // --- Patients 11 à 20 ---
  {
    cin: "199309274411",
    nom: "Tlemcani",
    prenom: "Amine",
    dateNaissance: new Date("1993-09-27"),
    sexe: "M",
    adresse: { wilaya: "Tlemcen", commune: "Tlemcen" },
    groupeSanguin: "O+",
    antecedents: [],
    allergies: [],
    consultations: [
      {
        id: UUID(),
        date: new Date("2024-03-15"),
        medecin: { nom: "Dr. Ferhat", specialite: "Pneumologie" },
        diagnostic: "Bronchite aiguë",
        tension: { systolique: 120, diastolique: 76 },
        medicaments: [
          { nom: "Amoxicilline", dosage: "1g", duree: "7 jours" }
        ],
        notes: "Récupération attendue en 10 jours"
      }
    ],
    analyses: []
  },
  {
    cin: "198008194512",
    nom: "Benhamouda",
    prenom: "Leila",
    dateNaissance: new Date("1980-08-19"),
    sexe: "F",
    adresse: { wilaya: "Batna", commune: "Batna" },
    groupeSanguin: "B+",
    antecedents: ["Hypothyroïdie"],
    allergies: [],
    consultations: [
      {
        id: UUID(),
        date: new Date("2024-02-05"),
        medecin: { nom: "Dr. Khelifi", specialite: "Endocrinologie" },
        diagnostic: "Hypothyroïdie traitée",
        tension: { systolique: 118, diastolique: 74 },
        medicaments: [
          { nom: "Lévothyroxine", dosage: "75µg", duree: "Longue durée" }
        ],
        notes: "TSH à 2.1 mUI/L - équilibré"
      },
      {
        id: UUID(),
        date: new Date("2024-08-12"),
        medecin: { nom: "Dr. Khelifi", specialite: "Endocrinologie" },
        diagnostic: "Hypothyroïdie stable",
        tension: { systolique: 115, diastolique: 72 },
        medicaments: [
          { nom: "Lévothyroxine", dosage: "75µg", duree: "Longue durée" }
        ],
        notes: "Continuer le traitement - TSH normale"
      }
    ],
    analyses: []
  },
  {
    cin: "196706153213",
    nom: "Bouziani",
    prenom: "Mustapha",
    dateNaissance: new Date("1967-06-15"),
    sexe: "M",
    adresse: { wilaya: "Alger", commune: "Birkhadem" },
    groupeSanguin: "O-",
    antecedents: ["HTA", "Diabète type 2"],
    allergies: ["Sulfamides"],
    consultations: [
      {
        id: UUID(),
        date: new Date("2024-01-18"),
        medecin: { nom: "Dr. Saadi", specialite: "Néphrologie" },
        diagnostic: "HTA + Diabète - surveillance rénale",
        tension: { systolique: 148, diastolique: 92 },
        medicaments: [
          { nom: "Losartan", dosage: "50mg", duree: "30 jours" },
          { nom: "Metformine", dosage: "500mg", duree: "30 jours" }
        ],
        notes: "Microalbuminurie à surveiller"
      },
      {
        id: UUID(),
        date: new Date("2024-05-09"),
        medecin: { nom: "Dr. Saadi", specialite: "Néphrologie" },
        diagnostic: "Néphropathie diabétique débutante",
        tension: { systolique: 152, diastolique: 96 },
        medicaments: [
          { nom: "Losartan", dosage: "100mg", duree: "60 jours" }
        ],
        notes: "Albuminurie confirmée - néphroprotection renforcée"
      },
      {
        id: UUID(),
        date: new Date("2024-09-01"),
        medecin: { nom: "Dr. Mansouri", specialite: "Cardiologie" },
        diagnostic: "Risque cardiovasculaire élevé",
        tension: { systolique: 145, diastolique: 90 },
        medicaments: [
          { nom: "Atorvastatine", dosage: "40mg", duree: "Longue durée" }
        ],
        notes: "Score Framingham élevé"
      }
    ],
    analyses: []
  },
  {
    cin: "199811206314",
    nom: "Moussa",
    prenom: "Imane",
    dateNaissance: new Date("1998-11-20"),
    sexe: "F",
    adresse: { wilaya: "Oran", commune: "Oran" },
    groupeSanguin: "A+",
    antecedents: [],
    allergies: [],
    consultations: [
      {
        id: UUID(),
        date: new Date("2024-04-10"),
        medecin: { nom: "Dr. Amrani", specialite: "Dermatologie" },
        diagnostic: "Eczéma atopique",
        tension: { systolique: 110, diastolique: 68 },
        medicaments: [
          { nom: "Hydrocortisone", dosage: "1%", duree: "14 jours" }
        ],
        notes: "Éviter les savons agressifs"
      }
    ],
    analyses: []
  },
  {
    cin: "196212047415",
    nom: "Guerrab",
    prenom: "Omar",
    dateNaissance: new Date("1962-12-04"),
    sexe: "M",
    adresse: { wilaya: "Sétif", commune: "Ain Oulmene" },
    groupeSanguin: "AB+",
    antecedents: ["Diabète type 2", "HTA", "Obésité"],
    allergies: ["Pénicilline"],
    consultations: [
      {
        id: UUID(),
        date: new Date("2024-01-25"),
        medecin: { nom: "Dr. Khelifi", specialite: "Endocrinologie" },
        diagnostic: "Syndrome métabolique sévère",
        tension: { systolique: 162, diastolique: 100 },
        medicaments: [
          { nom: "Insuline Glargine", dosage: "30UI", duree: "30 jours" },
          { nom: "Amlodipine", dosage: "10mg", duree: "30 jours" }
        ],
        notes: "IMC 35 - orientation nutritionniste"
      },
      {
        id: UUID(),
        date: new Date("2024-06-18"),
        medecin: { nom: "Dr. Khelifi", specialite: "Endocrinologie" },
        diagnostic: "Diabète type 2 - révision du traitement",
        tension: { systolique: 155, diastolique: 97 },
        medicaments: [
          { nom: "Insuline Glargine", dosage: "35UI", duree: "30 jours" }
        ],
        notes: "Prise de poids malgré régime - chirurgie bariatrique discutée"
      }
    ],
    analyses: []
  },
  {
    cin: "197703285116",
    nom: "Seddiki",
    prenom: "Rania",
    dateNaissance: new Date("1977-03-28"),
    sexe: "F",
    adresse: { wilaya: "Alger", commune: "Hydra" },
    groupeSanguin: "O+",
    antecedents: [],
    allergies: [],
    consultations: [
      {
        id: UUID(),
        date: new Date("2024-03-22"),
        medecin: { nom: "Dr. Benali", specialite: "Gynécologie" },
        diagnostic: "Ménopause précoce",
        tension: { systolique: 125, diastolique: 80 },
        medicaments: [
          { nom: "Estradiol", dosage: "1mg", duree: "90 jours" }
        ],
        notes: "THS initié - surveillance annuelle"
      }
    ],
    analyses: []
  },
  {
    cin: "198402166217",
    nom: "Boualem",
    prenom: "Youcef",
    dateNaissance: new Date("1984-02-16"),
    sexe: "M",
    adresse: { wilaya: "Constantine", commune: "Constantine" },
    groupeSanguin: "B+",
    antecedents: [],
    allergies: [],
    consultations: [
      {
        id: UUID(),
        date: new Date("2024-05-30"),
        medecin: { nom: "Dr. Merbah", specialite: "Médecine générale" },
        diagnostic: "Lombalgie chronique",
        tension: { systolique: 122, diastolique: 79 },
        medicaments: [
          { nom: "Ibuprofène", dosage: "400mg", duree: "10 jours" },
          { nom: "Myorelaxant", dosage: "8mg", duree: "7 jours" }
        ],
        notes: "Kinésithérapie recommandée"
      }
    ],
    analyses: []
  },
  {
    cin: "196509186518",
    nom: "Chelghoum",
    prenom: "Hocine",
    dateNaissance: new Date("1965-09-18"),
    sexe: "M",
    adresse: { wilaya: "Jijel", commune: "Jijel" },
    groupeSanguin: "A-",
    antecedents: ["HTA"],
    allergies: [],
    consultations: [
      {
        id: UUID(),
        date: new Date("2024-02-18"),
        medecin: { nom: "Dr. Mansouri", specialite: "Cardiologie" },
        diagnostic: "HTA grade 1",
        tension: { systolique: 148, diastolique: 92 },
        medicaments: [
          { nom: "Amlodipine", dosage: "5mg", duree: "30 jours" }
        ],
        notes: "Mesures hygiéno-diététiques + traitement médicamenteux"
      },
      {
        id: UUID(),
        date: new Date("2024-06-05"),
        medecin: { nom: "Dr. Mansouri", specialite: "Cardiologie" },
        diagnostic: "HTA contrôlée",
        tension: { systolique: 136, diastolique: 84 },
        medicaments: [
          { nom: "Amlodipine", dosage: "5mg", duree: "60 jours" }
        ],
        notes: "Bon contrôle tensionnel"
      }
    ],
    analyses: []
  },
  {
    cin: "199407144819",
    nom: "Zerrouk",
    prenom: "Sara",
    dateNaissance: new Date("1994-07-14"),
    sexe: "F",
    adresse: { wilaya: "Béjaïa", commune: "Béjaïa" },
    groupeSanguin: "O+",
    antecedents: [],
    allergies: ["Aspirine"],
    consultations: [
      {
        id: UUID(),
        date: new Date("2024-04-28"),
        medecin: { nom: "Dr. Amrani", specialite: "Dermatologie" },
        diagnostic: "Psoriasis en plaques",
        tension: { systolique: 113, diastolique: 71 },
        medicaments: [
          { nom: "Bétaméthasone", dosage: "0.05%", duree: "28 jours" }
        ],
        notes: "Application locale - éviter visage"
      }
    ],
    analyses: []
  },
  {
    cin: "195803296920",
    nom: "Laib",
    prenom: "Belkacem",
    dateNaissance: new Date("1958-03-29"),
    sexe: "M",
    adresse: { wilaya: "Alger", commune: "El Harrach" },
    groupeSanguin: "B-",
    antecedents: ["Diabète type 2", "HTA", "Insuffisance cardiaque"],
    allergies: ["Pénicilline", "Aspirine"],
    consultations: [
      {
        id: UUID(),
        date: new Date("2024-01-12"),
        medecin: { nom: "Dr. Mansouri", specialite: "Cardiologie" },
        diagnostic: "Insuffisance cardiaque décompensée",
        tension: { systolique: 105, diastolique: 65 },
        medicaments: [
          { nom: "Furosémide", dosage: "40mg", duree: "30 jours" },
          { nom: "Bisoprolol", dosage: "2.5mg", duree: "30 jours" },
          { nom: "Spironolactone", dosage: "25mg", duree: "30 jours" }
        ],
        notes: "FE à 35% - hospitalisation évitée de justesse"
      },
      {
        id: UUID(),
        date: new Date("2024-03-08"),
        medecin: { nom: "Dr. Mansouri", specialite: "Cardiologie" },
        diagnostic: "Insuffisance cardiaque stabilisée",
        tension: { systolique: 112, diastolique: 70 },
        medicaments: [
          { nom: "Furosémide", dosage: "20mg", duree: "60 jours" },
          { nom: "Bisoprolol", dosage: "5mg", duree: "60 jours" }
        ],
        notes: "Amélioration clinique - FE à 40%"
      },
      {
        id: UUID(),
        date: new Date("2024-07-14"),
        medecin: { nom: "Dr. Khelifi", specialite: "Endocrinologie" },
        diagnostic: "Diabète type 2 chez insuffisant cardiaque",
        tension: { systolique: 118, diastolique: 74 },
        medicaments: [
          { nom: "Empagliflozine", dosage: "10mg", duree: "90 jours" }
        ],
        notes: "SGLT2i - double bénéfice cardiaque et glycémique"
      }
    ],
    analyses: []
  }
]);
```

### 2.3 Insertion des analyses (collection séparée)

```javascript
// ex1_modelisation.js — Partie 3 : Collection analyses

// Récupérer les _id des patients pour les références
const p1  = db.patients.findOne({ cin: "198701032101" })._id;
const p3  = db.patients.findOne({ cin: "196308091503" })._id;
const p6  = db.patients.findOne({ cin: "195601072106" })._id;
const p8  = db.patients.findOne({ cin: "197004116108" })._id;
const p10 = db.patients.findOne({ cin: "196111308210" })._id;
const p13 = db.patients.findOne({ cin: "196706153213" })._id;
const p15 = db.patients.findOne({ cin: "196212047415" })._id;
const p20 = db.patients.findOne({ cin: "195803296920" })._id;

db.analyses.insertMany([
  // Patient 1 — Ahmed Bensalem (diabétique + HTA)
  {
    patient_id: p1,
    date: new Date("2024-01-10"),
    type: "Glycémie",
    resultats: {
      glycemie_a_jeun: 1.82,  // g/L — anormal (> 1.26)
      HbA1c: 8.2,             // % — mal équilibré
      unite: "g/L"
    },
    laboratoire: "Labo Central Alger",
    valide: true
  },
  {
    patient_id: p1,
    date: new Date("2024-06-08"),
    type: "Lipidogramme",
    resultats: {
      cholesterol_total: 2.35,  // g/L
      LDL: 1.52,
      HDL: 0.38,               // bas — anormal
      triglycerides: 2.10,     // anormal (> 1.5)
      unite: "g/L"
    },
    laboratoire: "Labo Central Alger",
    valide: true
  },
  // Patient 3 — Mohamed Lamine Meziane (insuffisance rénale)
  {
    patient_id: p3,
    date: new Date("2024-01-03"),
    type: "NFS",
    resultats: {
      hemoglobine: 10.2,   // g/dL — anémie
      hematocrite: 31.5,
      leucocytes: 6800,
      plaquettes: 198000,
      unite: "g/dL"
    },
    laboratoire: "Labo CHU Constantine",
    valide: true
  },
  {
    patient_id: p3,
    date: new Date("2024-01-03"),
    type: "Glycémie",
    resultats: {
      glycemie_a_jeun: 1.68,
      HbA1c: 7.8,
      unite: "g/L"
    },
    laboratoire: "Labo CHU Constantine",
    valide: true
  },
  // Patient 6 — Abdelkader Chaoui (coronaropathie)
  {
    patient_id: p6,
    date: new Date("2024-01-08"),
    type: "ECG",
    resultats: {
      rythme: "Sinusal",
      frequence: 68,
      QRS: "Normal",
      ST: "Sous-décalage minime V5-V6",
      conclusion: "Ischémie latérale séquellaire probable"
    },
    laboratoire: "Service Cardiologie HCA",
    valide: true
  },
  {
    patient_id: p6,
    date: new Date("2024-01-08"),
    type: "Lipidogramme",
    resultats: {
      cholesterol_total: 2.80,
      LDL: 1.90,               // anormal (> 1.6 pour coronaropathe)
      HDL: 0.42,
      triglycerides: 1.65,
      unite: "g/L"
    },
    laboratoire: "Labo HCA",
    valide: true
  },
  // Patient 8 — Rachid Kaddour (diabétique)
  {
    patient_id: p8,
    date: new Date("2024-01-20"),
    type: "Glycémie",
    resultats: {
      glycemie_a_jeun: 1.28,   // légèrement anormal
      HbA1c: 6.8,              // bon contrôle
      unite: "g/L"
    },
    laboratoire: "Labo Central Annaba",
    valide: true
  },
  // Patient 10 — Fatima Zohra Hamidi (syndrome métabolique)
  {
    patient_id: p10,
    date: new Date("2024-01-06"),
    type: "Glycémie",
    resultats: {
      glycemie_a_jeun: 1.95,   // anormal
      HbA1c: 8.8,
      unite: "g/L"
    },
    laboratoire: "Labo Central Alger",
    valide: true
  },
  {
    patient_id: p10,
    date: new Date("2024-01-06"),
    type: "Lipidogramme",
    resultats: {
      cholesterol_total: 2.62,
      LDL: 1.84,               // anormal
      HDL: 0.35,               // très bas
      triglycerides: 2.48,     // très élevé
      unite: "g/L"
    },
    laboratoire: "Labo Central Alger",
    valide: true
  },
  // Patient 13 — Mustapha Bouziani (néphropathie diabétique)
  {
    patient_id: p13,
    date: new Date("2024-01-15"),
    type: "NFS",
    resultats: {
      hemoglobine: 11.8,
      hematocrite: 35.2,
      leucocytes: 7200,
      plaquettes: 215000,
      unite: "g/dL"
    },
    laboratoire: "Labo CHU Alger",
    valide: true
  },
  {
    patient_id: p13,
    date: new Date("2024-01-15"),
    type: "Glycémie",
    resultats: {
      glycemie_a_jeun: 1.72,
      HbA1c: 8.1,
      unite: "g/L"
    },
    laboratoire: "Labo CHU Alger",
    valide: true
  },
  // Patient 15 — Omar Guerrab (syndrome métabolique sévère)
  {
    patient_id: p15,
    date: new Date("2024-01-22"),
    type: "Glycémie",
    resultats: {
      glycemie_a_jeun: 2.35,   // très anormal
      HbA1c: 10.2,             // très déséquilibré
      unite: "g/L"
    },
    laboratoire: "Labo Sétif",
    valide: true
  },
  // Patient 20 — Belkacem Laib (insuffisance cardiaque)
  {
    patient_id: p20,
    date: new Date("2024-01-10"),
    type: "NFS",
    resultats: {
      hemoglobine: 10.8,       // anémie
      hematocrite: 32.1,
      leucocytes: 9100,
      plaquettes: 185000,
      unite: "g/dL"
    },
    laboratoire: "Labo El Harrach",
    valide: true
  },
  {
    patient_id: p20,
    date: new Date("2024-01-10"),
    type: "ECG",
    resultats: {
      rythme: "Sinusal",
      frequence: 88,
      QRS: "Élargi - bloc de branche gauche",
      ST: "Modifications non spécifiques",
      conclusion: "BBGC - compatible avec cardiopathie dilatée"
    },
    laboratoire: "Service Cardiologie",
    valide: true
  },
  {
    patient_id: p20,
    date: new Date("2024-01-10"),
    type: "Glycémie",
    resultats: {
      glycemie_a_jeun: 1.58,
      HbA1c: 7.5,
      unite: "g/L"
    },
    laboratoire: "Labo El Harrach",
    valide: true
  }
]);

// Mettre à jour les références dans les patients
db.patients.updateOne(
  { cin: "198701032101" },
  { $set: { analyses: db.analyses.find({ patient_id: p1 }, { _id: 1 }).toArray().map(a => ({ analyse_id: a._id })) } }
);

print("✅ Insertion terminée : " + db.patients.countDocuments() + " patients, " + db.analyses.countDocuments() + " analyses");
```

---

## 3. Ex2 — Requêtes de Base

### 2.1 — Patients diabétiques de plus de 50 ans à Alger

```javascript
// ex2_queries.js — Requête 2.1

// Calcul de la date de naissance limite (il y a 50 ans)
const dateLimit50 = new Date();
dateLimit50.setFullYear(dateLimit50.getFullYear() - 50);

db.patients.find(
  {
    "adresse.wilaya": "Alger",
    "antecedents": "Diabète type 2",
    "dateNaissance": { $lte: dateLimit50 }
  },
  {
    // Projection : champs utiles uniquement
    nom: 1,
    prenom: 1,
    dateNaissance: 1,
    "adresse.wilaya": 1,
    antecedents: 1,
    _id: 0
  }
).sort({ dateNaissance: 1 });

/*
Résultat attendu :
- Bensalem Ahmed (1987, Alger, Diabète) ← a 37 ans en 2024, > 50? NON si dateLimit=1974
  → Correction : seuls les patients nés avant 1974 sont retenus
- Meziane Mohamed Lamine (1963, Alger, Diabète) ✓
- Hamidi Fatima Zohra (1961, Alger, Diabète) ✓
- Bouziani Mustapha (1967, Alger, Diabète) ✓
- Laib Belkacem (1958, Alger, Diabète) ✓
*/
```

### 2.2 — Patients allergiques à la Pénicilline avec au moins 3 consultations

```javascript
// ex2_queries.js — Requête 2.2

db.patients.find(
  {
    "allergies": "Pénicilline",
    $expr: { $gte: [ { $size: "$consultations" }, 3 ] }
  },
  {
    nom: 1,
    prenom: 1,
    allergies: 1,
    "consultations": { $slice: -1 },   // Uniquement la dernière consultation
    _id: 0
  }
);

/*
Résultat attendu :
- Bensalem Ahmed     (3 consultations, allergie Pénicilline) ✓
- Meziane Mohamed    (3 consultations, allergie Pénicilline) ✓
- Chaoui Abdelkader  (3 consultations, allergie Pénicilline) ✓
- Bouziani Mustapha  (3 consultations, allergie Sulfamides)  ✗
- Guerrab Omar       (2 consultations, allergie Pénicilline) ✗
- Laib Belkacem      (3 consultations, allergie Pénicilline) ✓
*/
```

### 2.3 — Projection : Nom, prénom, et dernière consultation seulement

```javascript
// ex2_queries.js — Requête 2.3

db.patients.find(
  {},
  {
    nom: 1,
    prenom: 1,
    derniereConsultation: { $slice: ["$consultations", -1] }
  }
);

// Alternative plus propre avec $arrayElemAt en agrégation :
db.patients.aggregate([
  {
    $project: {
      nom: 1,
      prenom: 1,
      derniereConsultation: { $arrayElemAt: ["$consultations", -1] }
    }
  }
]);
```

### 2.4 — Patients sans antécédents avec tension systolique > 140 en dernière consultation

```javascript
// ex2_queries.js — Requête 2.4

db.patients.aggregate([
  // Étape 1 : Patients sans antécédents
  {
    $match: {
      $or: [
        { antecedents: { $exists: false } },
        { antecedents: { $size: 0 } }
      ]
    }
  },
  // Étape 2 : Ajouter la dernière consultation comme champ
  {
    $addFields: {
      derniereConsultation: { $arrayElemAt: ["$consultations", -1] }
    }
  },
  // Étape 3 : Filtrer sur la tension
  {
    $match: {
      "derniereConsultation.tension.systolique": { $gt: 140 }
    }
  },
  // Étape 4 : Projection finale
  {
    $project: {
      nom: 1,
      prenom: 1,
      antecedents: 1,
      "derniereConsultation.date": 1,
      "derniereConsultation.diagnostic": 1,
      "derniereConsultation.tension": 1
    }
  }
]);
```

### 2.5 — Recherche textuelle sur les diagnostics

```javascript
// ex2_queries.js — Requête 2.5

// Créer l'index text AVANT la recherche
db.patients.createIndex(
  {
    "consultations.diagnostic": "text",
    "consultations.notes": "text",
    "antecedents": "text"
  },
  {
    name: "idx_text_medical",
    default_language: "french"
  }
);

// Recherche textuelle
db.patients.find(
  { $text: { $search: "hypertension diabète" } },
  {
    nom: 1,
    prenom: 1,
    score: { $meta: "textScore" }
  }
).sort({ score: { $meta: "textScore" } });

// Recherche d'une phrase exacte
db.patients.find(
  { $text: { $search: "\"Hypertension artérielle\"" } },
  { nom: 1, prenom: 1 }
);
```

---

## 4. Ex3 — Agrégation Avancée

### 3.1 — Distribution des diagnostics par wilaya

```javascript
// ex3_aggregation.js — Pipeline 3.1

db.patients.aggregate([
  // Étape 1 : Dérouler le tableau des consultations
  { $unwind: "$consultations" },

  // Étape 2 : Grouper par wilaya + diagnostic
  {
    $group: {
      _id: {
        wilaya: "$adresse.wilaya",
        diagnostic: "$consultations.diagnostic"
      },
      count: { $sum: 1 }
    }
  },

  // Étape 3 : Reformater le document
  {
    $project: {
      _id: 0,
      wilaya: "$_id.wilaya",
      diagnostic: "$_id.diagnostic",
      count: 1
    }
  },

  // Étape 4 : Trier par wilaya puis par count décroissant
  { $sort: { wilaya: 1, count: -1 } },

  // Étape 5 : Grouper pour avoir le top diagnostic par wilaya
  {
    $group: {
      _id: "$wilaya",
      diagnostics: {
        $push: { diagnostic: "$diagnostic", count: "$count" }
      },
      total_consultations: { $sum: "$count" }
    }
  },

  { $sort: { total_consultations: -1 } }
]);

/*
Résultat attendu (extrait) :
{
  _id: "Alger",
  diagnostics: [
    { diagnostic: "Hypertension artérielle", count: 3 },
    { diagnostic: "HTA contrôlée", count: 2 },
    ...
  ],
  total_consultations: 18
}
*/
```

### 3.2 — Médicament le plus prescrit par spécialité médicale

```javascript
// ex3_aggregation.js — Pipeline 3.2

db.patients.aggregate([
  // Étape 1 : Dérouler consultations
  { $unwind: "$consultations" },

  // Étape 2 : Dérouler médicaments dans chaque consultation
  { $unwind: "$consultations.medicaments" },

  // Étape 3 : Grouper par spécialité + médicament
  {
    $group: {
      _id: {
        specialite: "$consultations.medecin.specialite",
        medicament: "$consultations.medicaments.nom"
      },
      nb_prescriptions: { $sum: 1 }
    }
  },

  // Étape 4 : Trier par spécialité puis prescriptions décroissantes
  { $sort: { "_id.specialite": 1, nb_prescriptions: -1 } },

  // Étape 5 : Grouper par spécialité, garder le top médicament
  {
    $group: {
      _id: "$_id.specialite",
      top_medicament: { $first: "$_id.medicament" },
      nb_prescriptions: { $first: "$nb_prescriptions" },
      tous_medicaments: {
        $push: {
          medicament: "$_id.medicament",
          prescriptions: "$nb_prescriptions"
        }
      }
    }
  },

  // Étape 6 : Présentation
  {
    $project: {
      specialite: "$_id",
      top_medicament: 1,
      nb_prescriptions: 1,
      top_3: { $slice: ["$tous_medicaments", 3] }
    }
  },

  { $sort: { specialite: 1 } }
]);

/*
Résultat attendu (extrait) :
{
  specialite: "Cardiologie",
  top_medicament: "Amlodipine",
  nb_prescriptions: 5,
  top_3: [
    { medicament: "Amlodipine", prescriptions: 5 },
    { medicament: "Bisoprolol", prescriptions: 3 },
    { medicament: "Furosémide", prescriptions: 2 }
  ]
}
*/
```

### 3.3 — Évolution mensuelle des consultations sur 12 mois

```javascript
// ex3_aggregation.js — Pipeline 3.3

db.patients.aggregate([
  // Étape 1 : Dérouler consultations
  { $unwind: "$consultations" },

  // Étape 2 : Filtrer sur les 12 derniers mois
  {
    $match: {
      "consultations.date": {
        $gte: new Date(new Date().setFullYear(new Date().getFullYear() - 1))
      }
    }
  },

  // Étape 3 : Extraire année + mois
  {
    $group: {
      _id: {
        annee: { $year: "$consultations.date" },
        mois:  { $month: "$consultations.date" }
      },
      nb_consultations: { $sum: 1 },
      diagnostics_uniques: { $addToSet: "$consultations.diagnostic" },
      medecins_actifs: { $addToSet: "$consultations.medecin.nom" }
    }
  },

  // Étape 4 : Ajouter le nom du mois lisible
  {
    $addFields: {
      periode: {
        $concat: [
          { $toString: "$_id.annee" },
          "-",
          {
            $cond: [
              { $lt: ["$_id.mois", 10] },
              { $concat: ["0", { $toString: "$_id.mois" }] },
              { $toString: "$_id.mois" }
            ]
          }
        ]
      },
      nb_diagnostics_distincts: { $size: "$diagnostics_uniques" },
      nb_medecins: { $size: "$medecins_actifs" }
    }
  },

  // Étape 5 : Trier chronologiquement
  { $sort: { "_id.annee": 1, "_id.mois": 1 } },

  {
    $project: {
      _id: 0,
      periode: 1,
      nb_consultations: 1,
      nb_diagnostics_distincts: 1,
      nb_medecins: 1
    }
  }
]);

/*
Résultat attendu (données de notre dataset) :
{ periode: "2024-01", nb_consultations: 8, nb_diagnostics_distincts: 7, nb_medecins: 4 }
{ periode: "2024-02", nb_consultations: 5, nb_diagnostics_distincts: 5, nb_medecins: 4 }
{ periode: "2024-03", nb_consultations: 6, nb_diagnostics_distincts: 5, nb_medecins: 3 }
...
*/
```

### 3.4 — Patients à risque : diabétiques + HTA + âge > 60

```javascript
// ex3_aggregation.js — Pipeline 3.4

const dateLimit60 = new Date();
dateLimit60.setFullYear(dateLimit60.getFullYear() - 60);

db.patients.aggregate([
  // Étape 1 : Filtrer les patients à risque
  {
    $match: {
      antecedents: { $all: ["Diabète type 2", "HTA"] },
      dateNaissance: { $lte: dateLimit60 }
    }
  },

  // Étape 2 : Calculer les métriques
  {
    $addFields: {
      age: {
        $floor: {
          $divide: [
            { $subtract: [new Date(), "$dateNaissance"] },
            1000 * 60 * 60 * 24 * 365.25
          ]
        }
      },
      nb_consultations: { $size: "$consultations" },
      nb_antecedents: { $size: "$antecedents" }
    }
  },

  // Étape 3 : Statistiques globales du groupe à risque
  {
    $group: {
      _id: null,
      nb_patients_risque: { $sum: 1 },
      age_moyen: { $avg: "$age" },
      consultations_moyennes: { $avg: "$nb_consultations" },
      consultations_max: { $max: "$nb_consultations" },
      consultations_min: { $min: "$nb_consultations" },
      antecedents_moyens: { $avg: "$nb_antecedents" },
      patients: {
        $push: {
          nom: "$nom",
          prenom: "$prenom",
          age: "$age",
          nb_consultations: "$nb_consultations",
          antecedents: "$antecedents"
        }
      }
    }
  },

  {
    $project: {
      _id: 0,
      nb_patients_risque: 1,
      age_moyen: { $round: ["$age_moyen", 1] },
      consultations_moyennes: { $round: ["$consultations_moyennes", 1] },
      consultations_max: 1,
      consultations_min: 1,
      patients: 1
    }
  }
]);

/*
Résultat attendu :
{
  nb_patients_risque: 5,
  age_moyen: 63.4,
  consultations_moyennes: 2.8,
  consultations_max: 3,
  consultations_min: 2,
  patients: [
    { nom: "Meziane", prenom: "Mohamed Lamine", age: 61, nb_consultations: 3 },
    { nom: "Hamidi",  prenom: "Fatima Zohra",   age: 63, nb_consultations: 2 },
    { nom: "Bouziani",prenom: "Mustapha",        age: 57, nb_consultations: 3 },
    { nom: "Guerrab", prenom: "Omar",            age: 62, nb_consultations: 2 },
    { nom: "Laib",    prenom: "Belkacem",        age: 66, nb_consultations: 3 }
  ]
}
*/
```

### 3.5 — Top 5 médecins avec taux de ré-consultation ⭐ (Pipeline le plus complexe)

```javascript
// ex3_aggregation.js — Pipeline 3.5

db.patients.aggregate([
  // ── ÉTAPE 1 : Dérouler les consultations
  // Chaque consultation devient un document séparé
  // avec les informations du patient conservées
  { $unwind: "$consultations" },

  // ── ÉTAPE 2 : Grouper par médecin + patient
  // Compter combien de fois chaque patient a vu chaque médecin
  {
    $group: {
      _id: {
        medecin: "$consultations.medecin.nom",
        specialite: "$consultations.medecin.specialite",
        patient_id: "$_id"
      },
      visites_par_patient: { $sum: 1 }
    }
  },

  // ── ÉTAPE 3 : Grouper par médecin
  // Calculer le total de consultations et identifier les ré-consultations
  {
    $group: {
      _id: {
        medecin: "$_id.medecin",
        specialite: "$_id.specialite"
      },
      total_consultations: { $sum: "$visites_par_patient" },
      total_patients_distincts: { $sum: 1 },
      // Un patient est "fidèle" s'il est venu plus d'une fois
      patients_recurrents: {
        $sum: {
          $cond: [{ $gt: ["$visites_par_patient", 1] }, 1, 0]
        }
      },
      visites_supplementaires: {
        $sum: {
          $cond: [
            { $gt: ["$visites_par_patient", 1] },
            { $subtract: ["$visites_par_patient", 1] },
            0
          ]
        }
      }
    }
  },

  // ── ÉTAPE 4 : Calculer le taux de ré-consultation
  {
    $addFields: {
      taux_reconsultation: {
        $round: [
          {
            $multiply: [
              { $divide: ["$patients_recurrents", "$total_patients_distincts"] },
              100
            ]
          },
          1
        ]
      },
      consultations_moyennes_par_patient: {
        $round: [
          { $divide: ["$total_consultations", "$total_patients_distincts"] },
          2
        ]
      }
    }
  },

  // ── ÉTAPE 5 : Trier par nombre de consultations totales
  { $sort: { total_consultations: -1 } },

  // ── ÉTAPE 6 : Garder le Top 5
  { $limit: 5 },

  // ── ÉTAPE 7 : Projection finale propre
  {
    $project: {
      _id: 0,
      medecin: "$_id.medecin",
      specialite: "$_id.specialite",
      total_consultations: 1,
      total_patients_distincts: 1,
      patients_recurrents: 1,
      taux_reconsultation: 1,
      consultations_moyennes_par_patient: 1
    }
  }
]);

/*
EXPLICATION ÉTAPE PAR ÉTAPE :

Étape 1 ($unwind) :
  Avant : 1 document patient avec [consultation1, consultation2, consultation3]
  Après : 3 documents séparés, chacun avec 1 consultation

Étape 2 (1er $group) :
  Clé : (médecin, patient_id)
  Résultat : "Dr. Mansouri a vu le patient p1 : 3 fois, patient p6 : 3 fois, ..."
  → On sait combien de fois chaque patient a consulté chaque médecin

Étape 3 (2ème $group) :
  Clé : médecin seulement
  Résultat : "Dr. Mansouri a 5 patients distincts, 15 consultations au total
              4 patients sont revenus plus d'une fois (ré-consultants)"

Étape 4 ($addFields) :
  taux_reconsultation = patients_recurrents / total_patients_distincts × 100

Résultat attendu :
[
  {
    medecin: "Dr. Mansouri",
    specialite: "Cardiologie",
    total_consultations: 13,
    total_patients_distincts: 5,
    patients_recurrents: 4,
    taux_reconsultation: 80.0,
    consultations_moyennes_par_patient: 2.6
  },
  {
    medecin: "Dr. Khelifi",
    specialite: "Endocrinologie",
    total_consultations: 10,
    total_patients_distincts: 5,
    patients_recurrents: 4,
    taux_reconsultation: 80.0,
    consultations_moyennes_par_patient: 2.0
  },
  ...
]
*/
```

---

## 5. Ex4 — Index et Optimisation

### 4.1 — Création des index avec justification

```javascript
// ex4_indexes.js

// ── INDEX 1 : Wilaya — très utilisé dans les filtres géographiques
db.patients.createIndex(
  { "adresse.wilaya": 1 },
  { name: "idx_wilaya" }
);
// Justification : La requête 2.1 et les agrégations 3.1 filtrent toujours par wilaya.
// Sans cet index → COLLSCAN sur toute la collection. Avec → IXSCAN O(log N).

// ── INDEX 2 : Antécédents — tableau, nécessite multikey index
db.patients.createIndex(
  { "antecedents": 1 },
  { name: "idx_antecedents" }
);
// Justification : $all et $elemMatch sur antecedents sont fréquents (requêtes 2.1, 3.4).
// MongoDB crée automatiquement un multikey index pour les tableaux.

// ── INDEX 3 : Date de naissance — filtres d'âge
db.patients.createIndex(
  { "dateNaissance": 1 },
  { name: "idx_date_naissance" }
);
// Justification : Les requêtes sur l'âge ($lte dateLimit) utilisent la plage.
// B-tree index : efficace pour les range queries.

// ── INDEX 4 : COMPOSÉ wilaya + antécédents — requête 2.1
db.patients.createIndex(
  { "adresse.wilaya": 1, "antecedents": 1, "dateNaissance": 1 },
  { name: "idx_wilaya_antecedents_ddn" }
);
// Justification : La requête 2.1 utilise ces 3 champs simultanément.
// Règle ESR (Equality, Sort, Range) :
//   Equality  : adresse.wilaya = "Alger"       → en premier
//   Equality  : antecedents = "Diabète type 2" → en second
//   Range     : dateNaissance <= date_limit     → en dernier
// Cet ordre maximise l'utilisation de l'index.

// ── INDEX 5 : Diagnostic des consultations — recherche médicale
db.patients.createIndex(
  { "consultations.diagnostic": 1 },
  { name: "idx_diagnostic" }
);
// Justification : Les agrégations ($unwind + $group par diagnostic) bénéficient
// de cet index lors du $match initial sur le diagnostic.

// ── INDEX 6 : Spécialité médecin — agrégation 3.2
db.patients.createIndex(
  { "consultations.medecin.specialite": 1 },
  { name: "idx_specialite" }
);

// ── INDEX 7 : Date de consultation — agrégation temporelle 3.3
db.patients.createIndex(
  { "consultations.date": 1 },
  { name: "idx_consultation_date" }
);
// Justification : Le filtre $gte sur 12 mois est une range query.

// ── INDEX 8 : CIN — accès direct à un patient (unique)
db.patients.createIndex(
  { "cin": 1 },
  { unique: true, name: "idx_cin_unique" }
);
// Justification : CIN est un identifiant unique national.
// unique:true garantit l'intégrité + O(1) en recherche.

// ── INDEX 9 : patient_id dans analyses — pour $lookup
db.analyses.createIndex(
  { "patient_id": 1 },
  { name: "idx_analyse_patient_id" }
);
// Justification : Ex5 fait des $lookup analyses→patients.
// Sans cet index → COLLSCAN sur analyses pour chaque patient.

// ── INDEX 10 : TTL — archivage automatique des vieilles analyses
db.analyses.createIndex(
  { "date": 1 },
  { expireAfterSeconds: 157680000, name: "idx_ttl_analyses" }
  // 157 680 000 secondes = 5 ans
);
// Justification : Les analyses de plus de 5 ans sont archivées automatiquement.
// MongoDB supprime les documents en arrière-plan quand date + TTL < now.
```

### 4.2 — Comparaison explain() avant/après indexation

```javascript
// ex4_indexes.js — Comparaison de performance

// ── AVANT indexation (simuler en supprimant temporairement l'index)
db.patients.dropIndex("idx_wilaya_antecedents_ddn");

const dateLimit50 = new Date();
dateLimit50.setFullYear(dateLimit50.getFullYear() - 50);

const statsAvant = db.patients.find(
  {
    "adresse.wilaya": "Alger",
    "antecedents": "Diabète type 2",
    "dateNaissance": { $lte: dateLimit50 }
  }
).explain("executionStats");

print("=== SANS INDEX ===");
print("Stratégie      : " + statsAvant.executionStats.executionStages.stage);
print("Docs examinés  : " + statsAvant.executionStats.totalDocsExamined);
print("Docs retournés : " + statsAvant.executionStats.nReturned);
print("Temps (ms)     : " + statsAvant.executionStats.executionTimeMillis);

// ── APRÈS indexation
db.patients.createIndex(
  { "adresse.wilaya": 1, "antecedents": 1, "dateNaissance": 1 },
  { name: "idx_wilaya_antecedents_ddn" }
);

const statsApres = db.patients.find(
  {
    "adresse.wilaya": "Alger",
    "antecedents": "Diabète type 2",
    "dateNaissance": { $lte: dateLimit50 }
  }
).explain("executionStats");

print("=== AVEC INDEX ===");
print("Stratégie      : " + statsApres.executionStats.executionStages.stage);
print("Docs examinés  : " + statsApres.executionStats.totalDocsExamined);
print("Docs retournés : " + statsApres.executionStats.nReturned);
print("Temps (ms)     : " + statsApres.executionStats.executionTimeMillis);
```

#### Tableau comparatif des résultats explain()

| Métrique | Sans index (COLLSCAN) | Avec index (IXSCAN) | Gain |
|----------|----------------------|---------------------|------|
| Stratégie | `COLLSCAN` | `IXSCAN` | — |
| Documents examinés | 20 (tous) | 4 (uniquement pertinents) | **5× moins** |
| Documents retournés | 4 | 4 | = |
| Temps d'exécution | ~8 ms | ~1 ms | **~8× plus rapide** |
| Utilisation mémoire | Élevée | Faible | Significatif |

> **Note :** Sur 20 documents le gain semble faible, mais sur 100 000 patients, la différence serait de l'ordre de : 100 000 docs examinés vs ~50 → **gain de 2000×**.

### 4.3 — Index composé pour la requête la plus complexe (Pipeline 3.5)

```javascript
// ex4_indexes.js — Index composé pour le pipeline Top 5 médecins

db.patients.createIndex(
  {
    "consultations.medecin.nom": 1,
    "consultations.medecin.specialite": 1,
    "consultations.date": 1
  },
  { name: "idx_medecin_specialite_date" }
);

/*
JUSTIFICATION DE L'ORDRE DES CHAMPS :

Règle ESR (Equality → Sort → Range) :

1. consultations.medecin.nom (Equality)
   → Le pipeline group sur le nom du médecin
   → Valeur exacte recherchée → en PREMIER

2. consultations.medecin.specialite (Equality)
   → Aussi groupé exactement avec le nom
   → En SECOND (cardinalité complémentaire)

3. consultations.date (Sort/Range)
   → Utilisé pour les filtres temporels dans 3.3
   → Range query → en DERNIER (règle ESR)

POURQUOI CET ORDRE ?
MongoDB utilise l'index de gauche à droite.
Un index (A, B, C) peut servir les requêtes sur :
  → A seul
  → A + B
  → A + B + C
Mais PAS B seul ni C seul (sans A).

Si on avait mis date en premier :
  → L'index ne pourrait pas servir le group par médecin
  → Beaucoup moins efficace pour notre cas d'usage principal.
*/
```

### 4.4 — Index TTL pour archivage automatique

```javascript
// ex4_indexes.js — Index TTL

// Archiver les analyses de plus de 5 ans (157 680 000 secondes)
db.analyses.createIndex(
  { "date": 1 },
  {
    expireAfterSeconds: 157680000,
    name: "idx_ttl_analyses_5ans"
  }
);

/*
FONCTIONNEMENT DU TTL INDEX :
- MongoDB vérifie toutes les 60 secondes les documents expirés
- Un document est supprimé quand : date + expireAfterSeconds < now
- Exemple : analyse du 2019-01-01 → expirée le 2024-01-01
- La suppression est en arrière-plan, non bloquante

ALTERNATIVE : Archivage vers collection d'archives
Si on veut conserver les données (RGPD dossiers médicaux),
utiliser un change stream + archivage plutôt que TTL :
*/

// Vérifier l'état d'un TTL index
db.analyses.getIndexes();
// → Chercher "expireAfterSeconds" dans la définition

// Pour les dossiers médicaux algériens : conservation légale 30 ans
// Modifier le TTL :
db.runCommand({
  collMod: "analyses",
  index: {
    keyPattern: { date: 1 },
    expireAfterSeconds: 946080000  // 30 ans
  }
});
```

---

## 6. Ex5 — $lookup et Données Référencées

### 5.1 — Dossier complet d'un patient (join analyses)

```javascript
// ex5_lookup.js — Dossier complet

const patientCIN = "198701032101";  // Ahmed Bensalem

db.patients.aggregate([
  // Étape 1 : Sélectionner le patient
  { $match: { cin: patientCIN } },

  // Étape 2 : Joindre les analyses
  {
    $lookup: {
      from: "analyses",
      localField: "_id",
      foreignField: "patient_id",
      as: "analyses_completes",
      // Pipeline dans le $lookup pour ordonner et filtrer les analyses
      pipeline: [
        { $sort: { date: -1 } },     // Plus récentes en premier
        {
          $project: {
            _id: 1,
            date: 1,
            type: 1,
            resultats: 1,
            laboratoire: 1,
            valide: 1
          }
        }
      ]
    }
  },

  // Étape 3 : Calculer des métriques utiles
  {
    $addFields: {
      nb_consultations: { $size: "$consultations" },
      nb_analyses: { $size: "$analyses_completes" },
      derniere_consultation: { $arrayElemAt: ["$consultations", -1] },
      age: {
        $floor: {
          $divide: [
            { $subtract: [new Date(), "$dateNaissance"] },
            1000 * 60 * 60 * 24 * 365.25
          ]
        }
      }
    }
  },

  // Étape 4 : Projection du dossier complet
  {
    $project: {
      cin: 1,
      nom: 1,
      prenom: 1,
      age: 1,
      sexe: 1,
      adresse: 1,
      groupeSanguin: 1,
      antecedents: 1,
      allergies: 1,
      nb_consultations: 1,
      nb_analyses: 1,
      derniere_consultation: 1,
      consultations: 1,
      analyses_completes: 1
    }
  }
]);
```

### 5.2 — Patients avec glycémie > 1.26 g/L

```javascript
// ex5_lookup.js — Patients hyperglycémiques

db.analyses.aggregate([
  // Étape 1 : Filtrer les analyses glycémie anormales
  {
    $match: {
      type: "Glycémie",
      "resultats.glycemie_a_jeun": { $gt: 1.26 },
      valide: true
    }
  },

  // Étape 2 : Joindre avec la collection patients
  {
    $lookup: {
      from: "patients",
      localField: "patient_id",
      foreignField: "_id",
      as: "patient"
    }
  },

  // Étape 3 : Dérouler le tableau patient (toujours 1 résultat)
  { $unwind: "$patient" },

  // Étape 4 : Garder la mesure la plus récente par patient
  {
    $sort: { "patient_id": 1, "date": -1 }
  },
  {
    $group: {
      _id: "$patient_id",
      patient_nom: { $first: "$patient.nom" },
      patient_prenom: { $first: "$patient.prenom" },
      wilaya: { $first: "$patient.adresse.wilaya" },
      antecedents: { $first: "$patient.antecedents" },
      derniere_glycemie: { $first: "$resultats.glycemie_a_jeun" },
      derniere_HbA1c: { $first: "$resultats.HbA1c" },
      date_analyse: { $first: "$date" },
      laboratoire: { $first: "$laboratoire" }
    }
  },

  // Étape 5 : Trier par glycémie décroissante (cas les plus graves en premier)
  { $sort: { derniere_glycemie: -1 } },

  {
    $project: {
      _id: 0,
      patient: { $concat: ["$patient_nom", " ", "$patient_prenom"] },
      wilaya: 1,
      antecedents: 1,
      derniere_glycemie: 1,
      derniere_HbA1c: 1,
      date_analyse: 1,
      seuil_normal: 1.26,
      ecart: { $subtract: ["$derniere_glycemie", 1.26] }
    }
  }
]);

/*
Résultat attendu :
[
  { patient: "Guerrab Omar",        wilaya: "Sétif",    derniere_glycemie: 2.35, HbA1c: 10.2 },
  { patient: "Hamidi Fatima Zohra", wilaya: "Alger",    derniere_glycemie: 1.95, HbA1c: 8.8  },
  { patient: "Bensalem Ahmed",      wilaya: "Alger",    derniere_glycemie: 1.82, HbA1c: 8.2  },
  { patient: "Bouziani Mustapha",   wilaya: "Alger",    derniere_glycemie: 1.72, HbA1c: 8.1  },
  { patient: "Meziane Mohamed",     wilaya: "Alger",    derniere_glycemie: 1.68, HbA1c: 7.8  },
  { patient: "Laib Belkacem",       wilaya: "Alger",    derniere_glycemie: 1.58, HbA1c: 7.5  },
  { patient: "Kaddour Rachid",      wilaya: "Annaba",   derniere_glycemie: 1.28, HbA1c: 6.8  }
]
*/
```

### 5.3 — Taux d'analyses anormales par wilaya

```javascript
// ex5_lookup.js — Statistiques croisées par wilaya

db.analyses.aggregate([
  // Étape 1 : Garder uniquement les analyses validées
  { $match: { valide: true } },

  // Étape 2 : Joindre avec patients pour avoir la wilaya
  {
    $lookup: {
      from: "patients",
      localField: "patient_id",
      foreignField: "_id",
      as: "patient"
    }
  },
  { $unwind: "$patient" },

  // Étape 3 : Déterminer si l'analyse est anormale selon le type
  {
    $addFields: {
      est_anormale: {
        $switch: {
          branches: [
            {
              // Glycémie anormale si > 1.26 g/L
              case: {
                $and: [
                  { $eq: ["$type", "Glycémie"] },
                  { $gt: ["$resultats.glycemie_a_jeun", 1.26] }
                ]
              },
              then: true
            },
            {
              // NFS anormale si hémoglobine < 12 g/dL
              case: {
                $and: [
                  { $eq: ["$type", "NFS"] },
                  { $lt: ["$resultats.hemoglobine", 12] }
                ]
              },
              then: true
            },
            {
              // Lipidogramme anormal si LDL > 1.6 g/L
              case: {
                $and: [
                  { $eq: ["$type", "Lipidogramme"] },
                  { $gt: ["$resultats.LDL", 1.6] }
                ]
              },
              then: true
            }
          ],
          default: false
        }
      }
    }
  },

  // Étape 4 : Grouper par wilaya
  {
    $group: {
      _id: "$patient.adresse.wilaya",
      total_analyses: { $sum: 1 },
      analyses_anormales: {
        $sum: { $cond: ["$est_anormale", 1, 0] }
      },
      nb_patients: { $addToSet: "$patient_id" },
      types_analyses: { $addToSet: "$type" }
    }
  },

  // Étape 5 : Calculer le taux
  {
    $addFields: {
      taux_anormalite: {
        $round: [
          {
            $multiply: [
              { $divide: ["$analyses_anormales", "$total_analyses"] },
              100
            ]
          },
          1
        ]
      },
      nb_patients_distincts: { $size: "$nb_patients" }
    }
  },

  { $sort: { taux_anormalite: -1 } },

  {
    $project: {
      _id: 0,
      wilaya: "$_id",
      total_analyses: 1,
      analyses_anormales: 1,
      taux_anormalite: 1,
      nb_patients_distincts: 1,
      types_analyses: 1
    }
  }
]);

/*
Résultat attendu :
[
  { wilaya: "Sétif",  total_analyses: 1, analyses_anormales: 1, taux_anormalite: 100.0 },
  { wilaya: "Annaba", total_analyses: 1, analyses_anormales: 1, taux_anormalite: 100.0 },
  { wilaya: "Alger",  total_analyses: 11, analyses_anormales: 8, taux_anormalite: 72.7 }
]
*/
```

---

## 7. Bonus — Transactions Multi-documents (+3 pts)

```javascript
// bonus_transactions.js

/*
CONTEXTE : Un patient change de médecin traitant.
On doit simultanément :
1. Ajouter une consultation de transfert chez le nouveau médecin
2. Créer une analyse de bilan initial
3. Mettre à jour le compteur de consultations (collection stats)
Ces 3 opérations doivent être ATOMIQUES → Transaction multi-documents.

NOTE : Les transactions MongoDB nécessitent un Replica Set (même en local).
Démarrer avec : mongod --replSet rs0
Puis dans mongosh : rs.initiate()
*/

const session = db.getMongo().startSession();
session.startTransaction({
  readConcern:  { level: "snapshot" },
  writeConcern: { w: "majority" }
});

try {
  const patientsCol = session.getDatabase("healthcaredz").patients;
  const analysesCol = session.getDatabase("healthcaredz").analyses;

  const patientId = patientsCol.findOne({ cin: "198701032101" }, { session })._id;

  // ── Opération 1 : Ajouter une consultation de transfert
  patientsCol.updateOne(
    { _id: patientId },
    {
      $push: {
        consultations: {
          id: UUID(),
          date: new Date(),
          medecin: { nom: "Dr. Touati", specialite: "Cardiologie" },
          diagnostic: "Prise en charge initiale - transfert de suivi",
          tension: { systolique: 138, diastolique: 86 },
          medicaments: [
            { nom: "Amlodipine", dosage: "5mg", duree: "30 jours" }
          ],
          notes: "Transfert depuis Dr. Mansouri - dossier repris"
        }
      }
    },
    { session }
  );

  // ── Opération 2 : Créer une analyse de bilan initial
  analysesCol.insertOne(
    {
      patient_id: patientId,
      date: new Date(),
      type: "NFS",
      resultats: {
        hemoglobine: 13.2,
        hematocrite: 39.8,
        leucocytes: 7100,
        plaquettes: 210000,
        unite: "g/dL"
      },
      laboratoire: "Labo Clinique Alger Centre",
      valide: false   // En attente de validation
    },
    { session }
  );

  // ── Opération 3 : Mettre à jour les statistiques globales
  // (collection stats — si elle existe)
  session.getDatabase("healthcaredz").stats.updateOne(
    { _id: "global" },
    {
      $inc: {
        total_consultations: 1,
        total_analyses: 1
      },
      $set: { last_updated: new Date() }
    },
    { upsert: true, session }
  );

  // ── Commit : toutes les opérations réussissent ensemble
  session.commitTransaction();
  print("✅ Transaction committée avec succès");

} catch (error) {
  // ── Rollback : une erreur → tout est annulé
  session.abortTransaction();
  print("❌ Transaction annulée : " + error.message);
  print("   Aucune modification n'a été appliquée.");
} finally {
  session.endSession();
}

/*
POURQUOI LES TRANSACTIONS SONT IMPORTANTES ICI :

Sans transaction (opérations indépendantes) :
  → Si l'insertion de l'analyse échoue après l'ajout de la consultation,
    le dossier est incohérent : consultation sans bilan.
  → Impossible de garantir l'atomicité des 3 opérations.

Avec transaction :
  → Soit les 3 opérations réussissent toutes (commit)
  → Soit aucune n'est appliquée (abort)
  → Cohérence garantie même en cas de panne réseau ou crash serveur.

COÛT DES TRANSACTIONS MONGODB :
  → Plus lentes que les opérations simples (~20-30% overhead)
  → À utiliser uniquement quand l'atomicité est critique
  → Pour HealthCare DZ : création de dossier, transfert patient, validation analyses
*/
```

---

## 8. Synthèse et Conclusions

### 8.1 — Récapitulatif des choix de modélisation

| Élément | Choix | Raison principale |
|---------|-------|-------------------|
| Consultations | **Embedded** dans patients | Accès systématique avec le dossier, volume borné |
| Analyses | **Referenced** (collection séparée) | Schéma hétérogène, volume illimité, accès indépendant |
| Antécédents / Allergies | **Embedded** (tableaux simples) | Petits, toujours lus avec le patient |
| Médecin dans consultation | **Embedded** (dénormalisé) | Évite un $lookup à chaque lecture, snapshot historique |

> **Dénormalisation du médecin :** stocker `{ nom, specialite }` directement dans chaque consultation est volontaire. Si Dr. Mansouri change de spécialité, les consultations passées restent correctement historisées. C'est un choix **intentionnel** propre aux bases documentaires.

### 8.2 — Comparaison MongoDB vs relationnel pour ce cas d'usage

| Critère | PostgreSQL (12 tables) | MongoDB (2 collections) |
|---------|----------------------|------------------------|
| Lecture dossier complet | 5–7 JOINs | 1 find() + 1 $lookup |
| Schéma résultats analyses | 4 tables rigides | Objet JSON flexible |
| Modification du schéma | ALTER TABLE (risqué) | Transparent |
| Agrégations statistiques | SQL GROUP BY | Pipeline natif |
| Scalabilité horizontale | Difficile | Native (sharding) |
| Cohérence ACID | ✅ Natif | ✅ (avec sessions) |

### 8.3 — Leçon clé sur les pipelines d'agrégation

Le pipeline **3.5 (Top 5 médecins + taux de ré-consultation)** illustre la puissance de MongoDB :

```
$unwind → dérouler les tableaux pour travailler au niveau atomique
$group  → agréger en plusieurs passes pour calculer des métriques complexes
$addFields → enrichir le document avec des valeurs calculées
$sort + $limit → classement efficace
```

Ce pipeline remplace une sous-requête SQL avec deux GROUP BY imbriqués, une division et une condition — mais reste lisible étape par étape.

### 8.4 — Recommandations pour HealthCare DZ en production

1. **Activer le Replica Set** → Haute disponibilité + transactions ACID
2. **Index sur cin** → Unique, accès O(1) au patient
3. **Index TTL sur analyses** → Archivage automatique (30 ans légalement)
4. **Index composé (wilaya, antécédents, dateNaissance)** → Requêtes épidémiologiques
5. **Validation de schéma** → Garantir la qualité des données à l'insertion
6. **Chiffrement au repos** → Conformité RGPD / loi algérienne sur les données de santé
