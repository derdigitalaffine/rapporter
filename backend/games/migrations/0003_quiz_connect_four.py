import uuid

from django.db import migrations, models
import django.db.models.deletion


QUESTIONS = [
    ("mixed", "Welcher Planet hat die kürzeste Umlaufzeit um die Sonne?", "Which planet has the shortest orbital period around the Sun?", ["Merkur", "Venus", "Erde", "Mars"], ["Mercury", "Venus", "Earth", "Mars"], 0, "Merkur benötigt rund 88 Tage für einen Umlauf.", "Mercury takes about 88 days to orbit the Sun."),
    ("mixed", "Welche Sprache hat weltweit die meisten Muttersprachler?", "Which language has the largest number of native speakers worldwide?", ["Englisch", "Spanisch", "Mandarin-Chinesisch", "Hindi"], ["English", "Spanish", "Mandarin Chinese", "Hindi"], 2, "Mandarin-Chinesisch hat die größte Zahl an Muttersprachlern.", "Mandarin Chinese has the largest native-speaker population."),
    ("mixed", "In welchem Jahr fiel die Berliner Mauer?", "In which year did the Berlin Wall fall?", ["1987", "1988", "1989", "1990"], ["1987", "1988", "1989", "1990"], 2, "Die Maueröffnung war am 9. November 1989.", "The border opened on 9 November 1989."),
    ("mixed", "Welches Element hat das chemische Symbol W?", "Which element has the chemical symbol W?", ["Wolfram", "Wismut", "Wasserstoff", "Wolframium"], ["Tungsten", "Bismuth", "Hydrogen", "Wolframium"], 0, "W steht für Wolfram (englisch: tungsten).", "W denotes tungsten, from the name wolfram."),
    ("mixed", "Wer schrieb den Roman „Der Prozess“?", "Who wrote the novel The Trial?", ["Thomas Mann", "Franz Kafka", "Hermann Hesse", "Robert Musil"], ["Thomas Mann", "Franz Kafka", "Hermann Hesse", "Robert Musil"], 1, "„Der Prozess“ ist ein Roman von Franz Kafka.", "The Trial is a novel by Franz Kafka."),
    ("mixed", "Wie viele Flächen hat ein regelmäßiges Ikosaeder?", "How many faces does a regular icosahedron have?", ["12", "16", "20", "24"], ["12", "16", "20", "24"], 2, "Ein Ikosaeder besitzt 20 dreieckige Flächen.", "An icosahedron has 20 triangular faces."),
    ("mixed", "Welche Einheit misst elektrische Kapazität?", "Which unit measures electric capacitance?", ["Tesla", "Farad", "Weber", "Henry"], ["tesla", "farad", "weber", "henry"], 1, "Die SI-Einheit der Kapazität ist das Farad.", "The SI unit of capacitance is the farad."),
    ("physics_expert", "Für einen zeitunabhängigen Hamiltonoperator mit nichtentartetem Grundzustand liefert das Ritzsche Variationsprinzip für jeden normierten Versuchszustand welchen Zusammenhang?", "For a time-independent Hamiltonian with a non-degenerate ground state, what does the Rayleigh–Ritz variational principle state for any normalized trial state?", ["Der Erwartungswert liegt unter der Grundzustandsenergie.", "Der Erwartungswert ist gleich jeder Eigenenergie.", "Der Erwartungswert ist mindestens so groß wie die Grundzustandsenergie.", "Nur orthogonale Versuchszustände sind zulässig."], ["The expectation value is below the ground-state energy.", "The expectation value equals every eigenenergy.", "The expectation value is at least the ground-state energy.", "Only orthogonal trial states are allowed."], 2, "Der Energieerwartungswert eines normierten Versuchszustands ist eine obere Schranke für die Grundzustandsenergie.", "The energy expectation of a normalized trial state is an upper bound to the ground-state energy."),
    ("physics_expert", "Welche Symmetrie führt über den Satz von Noether zur Erhaltung der elektrischen Ladung in der QED?", "Which symmetry gives electric-charge conservation through Noether's theorem in QED?", ["Globale U(1)-Phasensymmetrie", "Räumliche Translation", "Zeitumkehr", "SU(2)-Isospin"], ["Global U(1) phase symmetry", "Spatial translation", "Time reversal", "SU(2) isospin"], 0, "Die globale U(1)-Phasensymmetrie des Materiefeldes erzeugt den erhaltenen Ladungsstrom.", "The global U(1) phase symmetry of the matter field yields the conserved charge current."),
    ("physics_expert", "Was charakterisiert im kanonischen Ensemble die Wärmekapazität bei konstantem Volumen direkt?", "In the canonical ensemble, what directly characterizes the heat capacity at constant volume?", ["Fluktuationen der Energie", "Fluktuationen der Teilchenzahl", "Nur den Mittelwert des Drucks", "Die Entropie ist exakt null"], ["Energy fluctuations", "Particle-number fluctuations", "Only the mean pressure", "Entropy is exactly zero"], 0, "Im kanonischen Ensemble ist die Energievarianz proportional zu k_B T² C_V.", "In the canonical ensemble the energy variance is proportional to k_B T² C_V."),
    ("physics_expert", "Welche Aussage über die Berry-Phase ist für eine adiabatisch zyklische Entwicklung korrekt?", "Which statement about the Berry phase is correct for an adiabatic cyclic evolution?", ["Sie hängt nur von der verstrichenen Zeit ab.", "Sie ist eine geometrische Phase, die vom Pfad im Parameterraum abhängt.", "Sie verschwindet für jeden nichtentarteten Zustand.", "Sie ist identisch mit der dynamischen Phase."], ["It depends only on elapsed time.", "It is a geometric phase depending on the path in parameter space.", "It vanishes for every non-degenerate state.", "It is identical to the dynamical phase."], 1, "Die Berry-Phase ist geometrisch und wird durch den geschlossenen Pfad im Parameterraum bestimmt.", "The Berry phase is geometric and determined by the closed path in parameter space."),
    ("physics_expert", "Für ein ideales entartetes Fermi-Gas bei T=0: Welche Zustände sind besetzt?", "For an ideal degenerate Fermi gas at T=0, which states are occupied?", ["Nur der Grundzustand", "Alle Einteilchenzustände bis zur Fermi-Energie", "Nur Zustände oberhalb der Fermi-Energie", "Eine Maxwell-Boltzmann-Verteilung"], ["Only the ground state", "All one-particle states up to the Fermi energy", "Only states above the Fermi energy", "A Maxwell–Boltzmann distribution"], 1, "Bei T=0 werden die Einteilchenzustände gemäß Pauli-Prinzip bis E_F aufgefüllt.", "At T=0, one-particle states are filled up to E_F according to the Pauli principle."),
    ("physics_expert", "Welche Größe bleibt bei einer Lorentz-Transformation zwischen Inertialsystemen invariant?", "Which quantity remains invariant under a Lorentz transformation between inertial frames?", ["Die räumliche Distanz allein", "Die Zeitspanne allein", "Das Minkowski-Intervall", "Die Newtonsche kinetische Energie"], ["Spatial distance alone", "Time interval alone", "The Minkowski interval", "Newtonian kinetic energy"], 2, "Das Raumzeitintervall ist ein Lorentz-Skalar.", "The spacetime interval is a Lorentz scalar."),
    ("physics_expert", "Welche Bedingung erfüllt ein physikalischer Zustand in der Coulomb-Eichung der klassischen Elektrodynamik als Nebenbedingung für das elektrische Feld?", "In classical electrodynamics, which constraint does the electric field satisfy through Gauss's law?", ["∇·E = ρ/ε₀", "∇×E = ρ/ε₀", "∇·B = ρ/ε₀", "∂E/∂t = 0 immer"], ["∇·E = ρ/ε₀", "∇×E = ρ/ε₀", "∇·B = ρ/ε₀", "∂E/∂t = 0 always"], 0, "Das Gaußsche Gesetz verknüpft die Divergenz des elektrischen Feldes mit der Ladungsdichte.", "Gauss's law relates the divergence of the electric field to charge density."),
    ("chemistry_expert", "Welche Größe ist bei konstantem T und p das geeignete Kriterium für Spontaneität in einem geschlossenen System?", "At constant T and p, which quantity is the appropriate spontaneity criterion for a closed system?", ["Helmholtz-Energie A", "Gibbs-Energie G", "Enthalpie H allein", "Innere Energie U allein"], ["Helmholtz energy A", "Gibbs energy G", "Enthalpy H alone", "Internal energy U alone"], 1, "Bei konstantem T und p verläuft ein spontaner Prozess in Richtung kleinerer Gibbs-Energie.", "At constant T and p, a spontaneous process proceeds toward lower Gibbs energy."),
    ("chemistry_expert", "Welche Auswahlregel gilt im harmonischen Oszillator-Näherungsmodell für fundamentale IR-Schwingungsübergänge?", "In the harmonic-oscillator approximation, what selection rule applies to fundamental IR vibrational transitions?", ["Δv = 0", "Δv = ±1", "Δv = ±2 ausschließlich", "Beliebiges Δv mit gleicher Wahrscheinlichkeit"], ["Δv = 0", "Δv = ±1", "Δv = ±2 only", "Any Δv with equal probability"], 1, "Für den ideal harmonischen Oszillator sind Übergänge mit Δv = ±1 erlaubt.", "For the ideal harmonic oscillator, transitions with Δv = ±1 are allowed."),
    ("chemistry_expert", "Was bedeutet eine negative chemische Verschiebungsanisotropie nicht allgemein; welche Aussage zur NMR-Abschirmung ist stattdessen grundlegend korrekt?", "Which statement about NMR chemical shielding is fundamentally correct?", ["Stärkere Abschirmung verschiebt Signale typischerweise zu kleinerem δ.", "Stärkere Abschirmung verschiebt Signale immer zu größerem δ.", "δ ist unabhängig von der elektronischen Umgebung.", "Nur Kernspin I=0 erzeugt NMR-Signale."], ["Greater shielding typically shifts signals to lower δ.", "Greater shielding always shifts signals to higher δ.", "δ is independent of electronic environment.", "Only nuclei with I=0 produce NMR signals."], 0, "Elektronische Abschirmung reduziert das effektive Magnetfeld am Kern und führt typischerweise zu kleinerem δ.", "Electronic shielding reduces the effective field at the nucleus and typically gives a lower δ."),
    ("chemistry_expert", "Welche Näherung trennt in der Quantenchemie aufgrund der großen Massendifferenz näherungsweise Kern- und Elektronenbewegung?", "Which approximation in quantum chemistry approximately separates nuclear and electronic motion because of their large mass difference?", ["Born-Oppenheimer-Näherung", "Debye-Hückel-Näherung", "Bragg-Bedingung", "Markov-Näherung"], ["Born–Oppenheimer approximation", "Debye–Hückel approximation", "Bragg condition", "Markov approximation"], 0, "Die Born-Oppenheimer-Näherung behandelt die Kerne auf der elektronischen Zeitskala näherungsweise als fest.", "The Born–Oppenheimer approximation treats nuclei as approximately fixed on the electronic timescale."),
    ("chemistry_expert", "Welche Aussage beschreibt ein chemisches Potential μ_i thermodynamisch?", "Which statement thermodynamically describes a chemical potential μ_i?", ["Partielle Ableitung der Gibbs-Energie nach der Stoffmenge i bei konstantem T, p und anderen Stoffmengen", "Gesamtenthalpie pro Mol unabhängig von der Zusammensetzung", "Nur die Aktivierungsenergie einer Reaktion", "Die Wärmekapazität bei konstantem Volumen"], ["Partial derivative of Gibbs energy with respect to amount of component i at constant T, p, and other amounts", "Total enthalpy per mole independent of composition", "Only a reaction activation energy", "Heat capacity at constant volume"], 0, "Das chemische Potential ist die partielle molare Gibbs-Energie.", "The chemical potential is the partial molar Gibbs energy."),
    ("chemistry_expert", "Für ein oktaedrisches Übergangsmetall-Komplexfeld: Wie spalten die fünf d-Orbitale im idealen O_h-Feld auf?", "For an octahedral transition-metal complex, how do the five d orbitals split in an ideal O_h field?", ["t₂g liegt energetisch unter e_g", "e_g liegt energetisch unter t₂g", "Alle bleiben exakt entartet", "Es entstehen drei gleich große Energieniveaus"], ["t₂g lies below e_g in energy", "e_g lies below t₂g in energy", "All remain exactly degenerate", "Three equally spaced energy levels form"], 0, "Im oktaedrischen Ligandenfeld werden d_xy, d_xz und d_yz als t₂g gegenüber e_g stabilisiert.", "In an octahedral ligand field, d_xy, d_xz, and d_yz form the lower-energy t₂g set relative to e_g."),
    ("chemistry_expert", "Welche Beziehung verknüpft im Übergangszustandsmodell die Geschwindigkeitskonstante mit der Gibbs-Aktivierungsenergie?", "Which relation connects a rate constant to the Gibbs free energy of activation in transition-state theory?", ["Eyring-Gleichung", "Beer-Lambert-Gesetz", "Nernst-Gleichung", "Clausius-Clapeyron-Gleichung"], ["Eyring equation", "Beer–Lambert law", "Nernst equation", "Clausius–Clapeyron equation"], 0, "Die Eyring-Gleichung beschreibt k über ΔG‡ und den Faktor k_B T/h.", "The Eyring equation expresses k through ΔG‡ and the factor k_B T/h."),
]


def seed_questions(apps, schema_editor):
    Question = apps.get_model("games", "QuizQuestion")
    for mode, prompt_de, prompt_en, options_de, options_en, correct_index, explanation_de, explanation_en in QUESTIONS:
        Question.objects.create(
            mode=mode,
            prompt_de=prompt_de,
            prompt_en=prompt_en,
            options_de=options_de,
            options_en=options_en,
            correct_index=correct_index,
            explanation_de=explanation_de,
            explanation_en=explanation_en,
            active=True,
        )


def remove_seed_questions(apps, schema_editor):
    Question = apps.get_model("games", "QuizQuestion")
    prompts = [row[1] for row in QUESTIONS]
    Question.objects.filter(prompt_de__in=prompts).delete()


class Migration(migrations.Migration):
    dependencies = [("games", "0002_gametaskassignment")]

    operations = [
        migrations.AlterField(
            model_name="gamematch",
            name="game_type",
            field=models.CharField(
                choices=[
                    ("rps", "Rock paper scissors"),
                    ("battleship", "Battleship"),
                    ("quiz", "Quiz duel"),
                    ("connect_four", "Connect Four"),
                ],
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="gamematch",
            name="quiz_mode",
            field=models.CharField(
                choices=[
                    ("mixed", "Mixed knowledge"),
                    ("physics_expert", "Physics expert"),
                    ("chemistry_expert", "Chemistry expert"),
                ],
                default="mixed",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="gamematch",
            name="quiz_round_count",
            field=models.PositiveSmallIntegerField(default=5),
        ),
        migrations.AddConstraint(
            model_name="gamematch",
            constraint=models.CheckConstraint(
                condition=models.Q(("quiz_round_count__gte", 3), ("quiz_round_count__lte", 7)),
                name="games_quiz_round_count_3_7",
            ),
        ),
        migrations.CreateModel(
            name="QuizQuestion",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("mode", models.CharField(choices=[("mixed", "Mixed knowledge"), ("physics_expert", "Physics expert"), ("chemistry_expert", "Chemistry expert")], db_index=True, max_length=24)),
                ("prompt_de", models.TextField()),
                ("prompt_en", models.TextField()),
                ("options_de", models.JSONField(default=list)),
                ("options_en", models.JSONField(default=list)),
                ("correct_index", models.PositiveSmallIntegerField()),
                ("explanation_de", models.TextField(blank=True)),
                ("explanation_en", models.TextField(blank=True)),
                ("active", models.BooleanField(db_index=True, default=True)),
            ],
            options={
                "ordering": ["mode", "created_at", "id"],
                "constraints": [models.CheckConstraint(condition=models.Q(("correct_index__lte", 5)), name="games_quiz_correct_index_lte_5")],
            },
        ),
        migrations.CreateModel(
            name="QuizRound",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("number", models.PositiveSmallIntegerField()),
                ("challenger_answer", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("opponent_answer", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("challenger_correct", models.BooleanField(blank=True, null=True)),
                ("opponent_correct", models.BooleanField(blank=True, null=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("match", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="quiz_rounds", to="games.gamematch")),
                ("question", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="rounds", to="games.quizquestion")),
            ],
            options={"ordering": ["number"], "constraints": [models.UniqueConstraint(fields=("match", "number"), name="games_quiz_round_unique")]},
        ),
        migrations.CreateModel(
            name="ConnectFourMove",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("column", models.PositiveSmallIntegerField()),
                ("row", models.PositiveSmallIntegerField()),
                ("sequence", models.PositiveSmallIntegerField()),
                ("match", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="connect_four_moves", to="games.gamematch")),
                ("player", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="connect_four_moves", to="family.membership")),
            ],
            options={
                "ordering": ["sequence"],
                "constraints": [
                    models.UniqueConstraint(fields=("match", "sequence"), name="games_connect4_sequence_unique"),
                    models.UniqueConstraint(fields=("match", "column", "row"), name="games_connect4_cell_unique"),
                    models.CheckConstraint(condition=models.Q(("column__lte", 6), ("row__lte", 5)), name="games_connect4_inside_board"),
                ],
            },
        ),
        migrations.RunPython(seed_questions, remove_seed_questions),
    ]
