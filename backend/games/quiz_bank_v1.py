"""Immutable source bank for the 500-question mixed quiz expansion.

Quizduell category names are used only as taxonomy. The factual pairs and all
prompt text here are original to FamilyOS; no proprietary question text is
copied. Keep this module stable because migration 0004 imports it.
"""

FORMS = {
    "books_words": ('Wer schrieb „{l}“?', 'Who wrote “{l}”?', 'Welches Werk stammt von {r}?', 'Which work was written by {r}?'),
    "comics": ('Wer schuf oder prägte „{l}“?', 'Who created or shaped “{l}”?', 'Welche Comicreihe ist eng mit {r} verbunden?', 'Which comic series is closely associated with {r}?'),
    "video_games": ('Welches Studio bzw. welcher Entwickler steckt hinter „{l}“?', 'Which studio or developer is behind “{l}”?', 'Welches Spiel stammt von {r}?', 'Which game was made by {r}?'),
    "the_2000s": ('In welchem Jahr der 2000er geschah: {l}?', 'In which year did this happen: {l}?', 'Welches Ereignis passt zum Jahr {r}?', 'Which event matches the year {r}?'),
    "outdoors": ('Wie lautet der wissenschaftliche Name von „{l}“?', 'What is the scientific name of the {l}?', 'Welche Art trägt den wissenschaftlichen Namen „{r}“?', 'Which species has the scientific name “{r}”?'),
    "food_drink": ('Mit welchem Land wird „{l}“ besonders verbunden?', 'Which country is especially associated with “{l}”?', 'Welche Spezialität passt zu {r}?', 'Which specialty is associated with {r}?'),
    "faith_religion": ('Welche Beschreibung passt zu „{l}“?', 'Which description matches “{l}”?', 'Welcher Begriff passt zu dieser Beschreibung: {r}?', 'Which term matches this description: {r}?'),
    "lab": ('Welches Elementsymbol gehört zu {l}?', 'Which chemical symbol belongs to {l}?', 'Welches Element hat das Symbol {r}?', 'Which element has the symbol {r}?'),
    "movies": ('Wer führte Regie bei „{l}“?', 'Who directed “{l}”?', 'Welcher Film wurde von {r} inszeniert?', 'Which film was directed by {r}?'),
    "body_mind": ('Welche Hauptfunktion passt zu „{l}“?', 'Which main function matches the {l}?', 'Welche Struktur passt zu dieser Funktion: {r}?', 'Which structure matches this function: {r}?'),
    "art_culture": ('Wer schuf „{l}“?', 'Who created “{l}”?', 'Welches Werk stammt von {r}?', 'Which artwork was created by {r}?'),
    "power_money": ('Welche Währung gehört zu {l}?', 'Which currency is used in {l}?', 'Welches Land nutzt {r}?', 'Which country uses the {r}?'),
    "media_entertainment": ('In welchem Jahr startete bzw. entstand „{l}“?', 'In which year did “{l}” launch or begin?', 'Welches Medienangebot passt zum Startjahr {r}?', 'Which media brand or service matches the start year {r}?'),
    "music_hits": ('Wer veröffentlichte den Song „{l}“?', 'Who released the song “{l}”?', 'Welcher Song ist mit {r} verbunden?', 'Which song is associated with {r}?'),
    "world": ('Was ist die Hauptstadt von {l}?', 'What is the capital of {l}?', 'Zu welchem Land gehört die Hauptstadt {r}?', 'Which country has {r} as its capital?'),
    "sports_leisure": ('Mit welcher Stadt ist „{l}“ besonders verbunden?', 'Which city is “{l}” especially associated with?', 'Welches Sportereignis ist mit {r} verbunden?', 'Which sporting event is associated with {r}?'),
    "tv_series": ('Wer entwickelte bzw. schuf die Serie „{l}“?', 'Who created or developed the series “{l}”?', 'Welche Serie ist mit {r} als Schöpfer verbunden?', 'Which series is associated with creator {r}?'),
    "technology": ('Welche Person ist besonders mit „{l}“ verbunden?', 'Which person is especially associated with “{l}”?', 'Welche Technik oder Entwicklung ist besonders mit {r} verbunden?', 'Which technology or development is especially associated with {r}?'),
    "history": ('In welchem Jahr geschah: {l}?', 'In which year did this happen: {l}?', 'Welches historische Ereignis passt zum Jahr {r}?', 'Which historical event matches the year {r}?'),
}

RAW = {
"books_words": """Faust I|Faust I|Johann Wolfgang von Goethe|Johann Wolfgang von Goethe
Der Prozess|The Trial|Franz Kafka|Franz Kafka
Buddenbrooks|Buddenbrooks|Thomas Mann|Thomas Mann
Effi Briest|Effi Briest|Theodor Fontane|Theodor Fontane
Stolz und Vorurteil|Pride and Prejudice|Jane Austen|Jane Austen
1984|Nineteen Eighty-Four|George Orwell|George Orwell
Der alte Mann und das Meer|The Old Man and the Sea|Ernest Hemingway|Ernest Hemingway
Hundert Jahre Einsamkeit|One Hundred Years of Solitude|Gabriel García Márquez|Gabriel García Márquez
Der Name der Rose|The Name of the Rose|Umberto Eco|Umberto Eco
Beloved|Beloved|Toni Morrison|Toni Morrison
Frankenstein|Frankenstein|Mary Shelley|Mary Shelley
Der Fremde|The Stranger|Albert Camus|Albert Camus
Der kleine Prinz|The Little Prince|Antoine de Saint-Exupéry|Antoine de Saint-Exupéry
Ulysses|Ulysses|James Joyce|James Joyce""",
"comics": """Asterix|Asterix|René Goscinny|René Goscinny
Tim und Struppi|The Adventures of Tintin|Hergé|Hergé
Peanuts|Peanuts|Charles M. Schulz|Charles M. Schulz
Calvin und Hobbes|Calvin and Hobbes|Bill Watterson|Bill Watterson
Mafalda|Mafalda|Quino|Quino
Garfield|Garfield|Jim Davis|Jim Davis
Lucky Luke|Lucky Luke|Morris|Morris
The Sandman|The Sandman|Neil Gaiman|Neil Gaiman
Persepolis|Persepolis|Marjane Satrapi|Marjane Satrapi
Bone|Bone|Jeff Smith|Jeff Smith
Hellboy|Hellboy|Mike Mignola|Mike Mignola
One Piece|One Piece|Eiichirō Oda|Eiichirō Oda
Dragon Ball|Dragon Ball|Akira Toriyama|Akira Toriyama
Watchmen|Watchmen|Alan Moore|Alan Moore""",
"video_games": """Minecraft|Minecraft|Mojang|Mojang
Portal|Portal|Valve|Valve
The Witcher 3: Wild Hunt|The Witcher 3: Wild Hunt|CD Projekt Red|CD Projekt Red
Hades|Hades|Supergiant Games|Supergiant Games
Celeste|Celeste|Maddy Makes Games|Maddy Makes Games
Stardew Valley|Stardew Valley|ConcernedApe|ConcernedApe
Hollow Knight|Hollow Knight|Team Cherry|Team Cherry
Disco Elysium|Disco Elysium|ZA/UM|ZA/UM
Journey|Journey|thatgamecompany|thatgamecompany
Baldur’s Gate 3|Baldur’s Gate 3|Larian Studios|Larian Studios
Ori and the Blind Forest|Ori and the Blind Forest|Moon Studios|Moon Studios
Cuphead|Cuphead|Studio MDHR|Studio MDHR
Dead Cells|Dead Cells|Motion Twin|Motion Twin
Outer Wilds|Outer Wilds|Mobius Digital|Mobius Digital""",
"the_2000s": """Erster Entwurf des menschlichen Genoms veröffentlicht|First draft of the human genome published|2000|2000
Wikipedia geht online|Wikipedia launches|2001|2001
Euro-Bargeld wird eingeführt|Euro banknotes and coins enter circulation|2002|2002
Humangenomprojekt wird abgeschlossen|Human Genome Project is completed|2003|2003
Facebook wird gegründet|Facebook is founded|2004|2004
YouTube wird gegründet|YouTube is founded|2005|2005
Pluto wird als Zwergplanet eingestuft|Pluto is classified as a dwarf planet|2006|2006
Erstes iPhone kommt auf den Markt|First iPhone goes on sale|2007|2007
Large Hadron Collider nimmt den Betrieb auf|Large Hadron Collider starts operating|2008|2008
Bitcoin startet mit dem Genesis-Block|Bitcoin launches with the genesis block|2009|2009
Instagram wird gestartet|Instagram launches|2010|2010
Letzter Space-Shuttle-Flug landet|Final Space Shuttle mission lands|2011|2011
Higgs-Boson wird am CERN bekanntgegeben|CERN announces the Higgs boson discovery|2012|2012""",
"outdoors": """Rotfuchs|Red fox|Vulpes vulpes|Vulpes vulpes
Eichhörnchen|Red squirrel|Sciurus vulgaris|Sciurus vulgaris
Braunbär|Brown bear|Ursus arctos|Ursus arctos
Wolf|Grey wolf|Canis lupus|Canis lupus
Luchs|Eurasian lynx|Lynx lynx|Lynx lynx
Dachs|European badger|Meles meles|Meles meles
Igel|European hedgehog|Erinaceus europaeus|Erinaceus europaeus
Steinadler|Golden eagle|Aquila chrysaetos|Aquila chrysaetos
Weißstorch|White stork|Ciconia ciconia|Ciconia ciconia
Wanderfalke|Peregrine falcon|Falco peregrinus|Falco peregrinus
Buche|European beech|Fagus sylvatica|Fagus sylvatica
Stieleiche|English oak|Quercus robur|Quercus robur
Löwenzahn|Common dandelion|Taraxacum officinale|Taraxacum officinale""",
"food_drink": """Sushi|Sushi|Japan|Japan
Paella|Paella|Spanien|Spain
Feijoada|Feijoada|Brasilien|Brazil
Poutine|Poutine|Kanada|Canada
Pho|Pho|Vietnam|Vietnam
Ceviche|Ceviche|Peru|Peru
Moussaka|Moussaka|Griechenland|Greece
Bibimbap|Bibimbap|Südkorea|South Korea
Gulasch|Goulash|Ungarn|Hungary
Tagine|Tagine|Marokko|Morocco
Pierogi|Pierogi|Polen|Poland
Khachapuri|Khachapuri|Georgien|Georgia
Adobo|Adobo|Philippinen|Philippines""",
"faith_religion": """Ramadan|Ramadan|Fastenmonat im Islam|month of fasting in Islam
Diwali|Diwali|Lichterfest in hinduistischen Traditionen|festival of lights in Hindu traditions
Pessach|Passover|jüdisches Fest zur Erinnerung an den Exodus|Jewish festival commemorating the Exodus
Vesakh|Vesak|buddhistisches Fest zu Ehren Buddhas|Buddhist festival honoring the Buddha
Sabbat|Shabbat|jüdischer wöchentlicher Ruhetag|Jewish weekly day of rest
Eucharistie|Eucharist|christliches Sakrament mit Brot und Wein|Christian sacrament involving bread and wine
Haddsch|Hajj|islamische Pilgerfahrt nach Mekka|Islamic pilgrimage to Mecca
Torah|Torah|zentraler Textbestand des Judentums|central sacred text of Judaism
Tripitaka|Tripitaka|buddhistischer Kanon heiliger Texte|Buddhist canon of sacred texts
Guru Granth Sahib|Guru Granth Sahib|heilige Schrift des Sikhismus|sacred scripture of Sikhism
Upanishaden|Upanishads|philosophische Schriften hinduistischer Traditionen|philosophical texts in Hindu traditions
Bodhi|Bodhi|Begriff für Erwachen im Buddhismus|term for awakening in Buddhism
Zakat|Zakat|verpflichtende Almosengabe im Islam|obligatory charitable giving in Islam""",
"lab": """Wasserstoff|Hydrogen|H|H
Helium|Helium|He|He
Kohlenstoff|Carbon|C|C
Stickstoff|Nitrogen|N|N
Sauerstoff|Oxygen|O|O
Natrium|Sodium|Na|Na
Magnesium|Magnesium|Mg|Mg
Aluminium|Aluminium|Al|Al
Silicium|Silicon|Si|Si
Phosphor|Phosphorus|P|P
Schwefel|Sulfur|S|S
Chlor|Chlorine|Cl|Cl
Kalium|Potassium|K|K
Eisen|Iron|Fe|Fe""",
"movies": """Der Pate|The Godfather|Francis Ford Coppola|Francis Ford Coppola
Pulp Fiction|Pulp Fiction|Quentin Tarantino|Quentin Tarantino
Parasite|Parasite|Bong Joon-ho|Bong Joon-ho
Spirited Away|Spirited Away|Hayao Miyazaki|Hayao Miyazaki
Moonlight|Moonlight|Barry Jenkins|Barry Jenkins
Mad Max: Fury Road|Mad Max: Fury Road|George Miller|George Miller
Roma|Roma|Alfonso Cuarón|Alfonso Cuarón
Lost in Translation|Lost in Translation|Sofia Coppola|Sofia Coppola
Get Out|Get Out|Jordan Peele|Jordan Peele
Portrait einer jungen Frau in Flammen|Portrait of a Lady on Fire|Céline Sciamma|Céline Sciamma
Oldboy|Oldboy|Park Chan-wook|Park Chan-wook
Mulholland Drive|Mulholland Drive|David Lynch|David Lynch
The Grand Budapest Hotel|The Grand Budapest Hotel|Wes Anderson|Wes Anderson""",
"body_mind": """Hippocampus|Hippocampus|Gedächtnisbildung|memory formation
Kleinhirn|Cerebellum|Koordination von Bewegungen|coordination of movement
Netzhaut|Retina|Umwandlung von Lichtreizen in Nervensignale|conversion of light into neural signals
Alveolen|Alveoli|Gasaustausch in der Lunge|gas exchange in the lungs
Nephron|Nephron|Filtration und Aufbereitung des Harns|filtration and processing of urine
Bauchspeicheldrüse|Pancreas|Bildung von Verdauungsenzymen und Hormonen|production of digestive enzymes and hormones
Schilddrüse|Thyroid gland|Bildung von Schilddrüsenhormonen|production of thyroid hormones
Milz|Spleen|Filterung des Blutes und Immunfunktion|blood filtration and immune function
Sehne|Tendon|Verbindung von Muskel und Knochen|connection of muscle to bone
Band|Ligament|Verbindung von Knochen mit Knochen|connection of bone to bone
Hornhaut|Cornea|Lichtbrechung an der Vorderseite des Auges|refraction of light at the front of the eye
Myelin|Myelin|elektrische Isolation von Nervenfasern|electrical insulation of nerve fibers
Thrombozyten|Platelets|Blutgerinnung|blood clotting""",
"art_culture": """Mona Lisa|Mona Lisa|Leonardo da Vinci|Leonardo da Vinci
Die Sternennacht|The Starry Night|Vincent van Gogh|Vincent van Gogh
Der Kuss|The Kiss|Gustav Klimt|Gustav Klimt
Guernica|Guernica|Pablo Picasso|Pablo Picasso
Die Beständigkeit der Erinnerung|The Persistence of Memory|Salvador Dalí|Salvador Dalí
Nighthawks|Nighthawks|Edward Hopper|Edward Hopper
American Gothic|American Gothic|Grant Wood|Grant Wood
Die große Welle vor Kanagawa|The Great Wave off Kanagawa|Katsushika Hokusai|Katsushika Hokusai
Das Mädchen mit dem Perlenohrring|Girl with a Pearl Earring|Johannes Vermeer|Johannes Vermeer
Die Geburt der Venus|The Birth of Venus|Sandro Botticelli|Sandro Botticelli
Der Wanderer über dem Nebelmeer|Wanderer above the Sea of Fog|Caspar David Friedrich|Caspar David Friedrich
Las Meninas|Las Meninas|Diego Velázquez|Diego Velázquez
Der Schrei|The Scream|Edvard Munch|Edvard Munch""",
"power_money": """Japan|Japan|Yen|yen
Schweiz|Switzerland|Schweizer Franken|Swiss franc
Polen|Poland|Złoty|złoty
Tschechien|Czechia|Tschechische Krone|Czech koruna
Ungarn|Hungary|Forint|forint
Schweden|Sweden|Schwedische Krone|Swedish krona
Norwegen|Norway|Norwegische Krone|Norwegian krone
Dänemark|Denmark|Dänische Krone|Danish krone
Indien|India|Indische Rupie|Indian rupee
Südkorea|South Korea|Won|won
Mexiko|Mexico|Mexikanischer Peso|Mexican peso
Brasilien|Brazil|Real|real
Südafrika|South Africa|Rand|rand""",
"media_entertainment": """Time|Time|1923|1923
The New Yorker|The New Yorker|1925|1925
BBC Television Service|BBC Television Service|1936|1936
Playboy|Playboy|1953|1953
CNN|CNN|1980|1980
MTV|MTV|1981|1981
The Independent|The Independent|1986|1986
IMDb|IMDb|1990|1990
Amazon|Amazon|1994|1994
Netflix|Netflix|1997|1997
Google|Google|1998|1998
YouTube|YouTube|2005|2005
Spotify|Spotify|2006|2006""",
"music_hits": """Respect|Respect|Aretha Franklin|Aretha Franklin
Purple Rain|Purple Rain|Prince|Prince
Like a Prayer|Like a Prayer|Madonna|Madonna
Smells Like Teen Spirit|Smells Like Teen Spirit|Nirvana|Nirvana
Crazy in Love|Crazy in Love|Beyoncé|Beyoncé
Rolling in the Deep|Rolling in the Deep|Adele|Adele
Heroes|Heroes|David Bowie|David Bowie
Fast Car|Fast Car|Tracy Chapman|Tracy Chapman
Take On Me|Take On Me|a-ha|a-ha
Paper Planes|Paper Planes|M.I.A.|M.I.A.
Seven Nation Army|Seven Nation Army|The White Stripes|The White Stripes
Royals|Royals|Lorde|Lorde
Blinding Lights|Blinding Lights|The Weeknd|The Weeknd""",
"world": """Kanada|Canada|Ottawa|Ottawa
Australien|Australia|Canberra|Canberra
Brasilien|Brazil|Brasília|Brasília
Japan|Japan|Tokio|Tokyo
Neuseeland|New Zealand|Wellington|Wellington
Marokko|Morocco|Rabat|Rabat
Kenia|Kenya|Nairobi|Nairobi
Argentinien|Argentina|Buenos Aires|Buenos Aires
Thailand|Thailand|Bangkok|Bangkok
Island|Iceland|Reykjavík|Reykjavík
Portugal|Portugal|Lissabon|Lisbon
Vietnam|Vietnam|Hanoi|Hanoi
Finnland|Finland|Helsinki|Helsinki
Peru|Peru|Lima|Lima""",
"sports_leisure": """Wimbledon|Wimbledon|London|London
Boston Marathon|Boston Marathon|Boston|Boston
24 Stunden von Le Mans|24 Hours of Le Mans|Le Mans|Le Mans
Indianapolis 500|Indianapolis 500|Indianapolis|Indianapolis
Großer Preis von Monaco|Monaco Grand Prix|Monte-Carlo|Monte Carlo
Tour de France: traditionelle Schlussetappe|Tour de France: traditional final stage|Paris|Paris
Australian Open|Australian Open|Melbourne|Melbourne
US Open Tennis|US Open Tennis|New York|New York
The Masters|The Masters|Augusta|Augusta
Kentucky Derby|Kentucky Derby|Louisville|Louisville
Henley Royal Regatta|Henley Royal Regatta|Henley-on-Thames|Henley-on-Thames
Hahnenkammrennen|Hahnenkamm Races|Kitzbühel|Kitzbühel
24 Stunden von Daytona|24 Hours of Daytona|Daytona Beach|Daytona Beach""",
"tv_series": """Breaking Bad|Breaking Bad|Vince Gilligan|Vince Gilligan
The Wire|The Wire|David Simon|David Simon
Fleabag|Fleabag|Phoebe Waller-Bridge|Phoebe Waller-Bridge
Mad Men|Mad Men|Matthew Weiner|Matthew Weiner
Succession|Succession|Jesse Armstrong|Jesse Armstrong
Atlanta|Atlanta|Donald Glover|Donald Glover
The Good Place|The Good Place|Michael Schur|Michael Schur
Dark|Dark|Baran bo Odar|Baran bo Odar
Derry Girls|Derry Girls|Lisa McGee|Lisa McGee
Reservation Dogs|Reservation Dogs|Sterlin Harjo|Sterlin Harjo
Severance|Severance|Dan Erickson|Dan Erickson
Ted Lasso|Ted Lasso|Bill Lawrence|Bill Lawrence
Better Call Saul|Better Call Saul|Peter Gould|Peter Gould""",
"technology": """World Wide Web|World Wide Web|Tim Berners-Lee|Tim Berners-Lee
Linux-Kernel|Linux kernel|Linus Torvalds|Linus Torvalds
Programmiersprache Python|Python programming language|Guido van Rossum|Guido van Rossum
Programmiersprache Java|Java programming language|James Gosling|James Gosling
Programmiersprache C|C programming language|Dennis Ritchie|Dennis Ritchie
Ethernet|Ethernet|Robert Metcalfe|Robert Metcalfe
QR-Code|QR Code|Masahiro Hara|Masahiro Hara
Dynamit|Dynamite|Alfred Nobel|Alfred Nobel
Dieselmotor|Diesel engine|Rudolf Diesel|Rudolf Diesel
Brailleschrift|Braille|Louis Braille|Louis Braille
Morsecode|Morse code|Samuel Morse|Samuel Morse
Phonograph|Phonograph|Thomas Edison|Thomas Edison""",
"history": """Normannische Eroberung Englands|Norman conquest of England|1066|1066
Magna Carta wird besiegelt|Magna Carta is sealed|1215|1215
Kolumbus erreicht die Karibik|Columbus reaches the Caribbean|1492|1492
Reformation: Luthers 95 Thesen|Reformation: Luther's 95 Theses|1517|1517
Westfälischer Frieden|Peace of Westphalia|1648|1648
Amerikanische Unabhängigkeitserklärung|United States Declaration of Independence|1776|1776
Sturm auf die Bastille|Storming of the Bastille|1789|1789
Wiener Kongress endet|Congress of Vienna concludes|1815|1815
Deutsches Kaiserreich wird gegründet|German Empire is proclaimed|1871|1871
Erster Weltkrieg beginnt|First World War begins|1914|1914
Zweiter Weltkrieg endet in Europa|Second World War ends in Europe|1945|1945
Fall der Berliner Mauer|Fall of the Berlin Wall|1989|1989""",
}

FACTS = {key: [tuple(line.split("|")) for line in value.splitlines() if line.strip()] for key, value in RAW.items()}


def build_questions(category_labels):
    """Return 500 validated question dicts, two directions per factual pair."""
    questions = []
    for category, facts in FACTS.items():
        form_de, form_en, inverse_de, inverse_en = FORMS[category]
        label_de = category_labels[category]["de"]
        label_en = category_labels[category]["en"]
        for index, (lde, len_, rde, ren) in enumerate(facts):
            peers = [facts[(index + step) % len(facts)] for step in range(1, 4)]
            correct_index = index % 4
            options_de = [peer[2] for peer in peers]
            options_en = [peer[3] for peer in peers]
            options_de.insert(correct_index, rde)
            options_en.insert(correct_index, ren)
            questions.append({
                "category": category,
                "prompt_de": f"{label_de} · {form_de.format(l=lde, r=rde)}",
                "prompt_en": f"{label_en} · {form_en.format(l=len_, r=ren)}",
                "options_de": options_de,
                "options_en": options_en,
                "correct_index": correct_index,
                "explanation_de": f"{lde} — {rde}.",
                "explanation_en": f"{len_} — {ren}.",
            })
            correct_index = (index + 2) % 4
            options_de = [peer[0] for peer in peers]
            options_en = [peer[1] for peer in peers]
            options_de.insert(correct_index, lde)
            options_en.insert(correct_index, len_)
            questions.append({
                "category": category,
                "prompt_de": f"{label_de} · {inverse_de.format(l=lde, r=rde)}",
                "prompt_en": f"{label_en} · {inverse_en.format(l=len_, r=ren)}",
                "options_de": options_de,
                "options_en": options_en,
                "correct_index": correct_index,
                "explanation_de": f"{lde} — {rde}.",
                "explanation_en": f"{len_} — {ren}.",
            })
    if len(questions) != 500:
        raise RuntimeError(f"Expected exactly 500 questions, got {len(questions)}")
    for question in questions:
        if len(question["options_de"]) != 4 or len(set(question["options_de"])) != 4:
            raise RuntimeError(f"Non-unique German options in {question['prompt_de']}")
        if len(question["options_en"]) != 4 or len(set(question["options_en"])) != 4:
            raise RuntimeError(f"Non-unique English options in {question['prompt_en']}")
    return questions
