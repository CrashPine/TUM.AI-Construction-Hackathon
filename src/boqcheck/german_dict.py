"""Bundled German construction and BoQ vocabulary dictionary.

Provides a set of common German construction terms, trade names, units,
and general vocabulary for typo detection in bills of quantities (LV).
"""

from __future__ import annotations

# Common German construction and LV vocabulary (~450 entries).
_WORDS = """
abbrechen abdichten abdichtung abdeckung abfall abfluss abgang abgabe abmessung
abnahme abpackung abscheiden abschnitt abstand abtrag abzweig acryl allfällig
allgemein altbau angebot anordnung anpassen anstrich antrag antwort anzahl arbeiten
armierung asphalt aufbau aufforderung auflage aufmass aufnahme aufpreis auftrag
ausbildung ausbau ausblasen ausführung aushub ausklinkung ausschreibung bauelement
baugewerbe baugrund bauherr bauholz bauleitung baumaßnahme baustelle baustrom bauteil
bauwerk bedarfposition befestigung behang behälter beidseitig bekleidung belag
beleuchtung belüftung bemerkung bemessung bereich beschichtung beschreibung beseitigen
bestandteil bestätigung beton betonfertigteil betongüte betonsockel betonstahl
bewehrung bezeichnung bieter bindemittel bitumen blank blech blockzarge blende
boden bodenablauf bodenbelag bodenplatte bohrung bohle bordstein böschung brandschutz
breite bruchstein brüstung bürste büro bündig dach dachablauf dachabdichtung
dachbegrünung dachdeckung dachhaut dämmstoff dämmung decke deckel deckschicht
demontage dichte dichtung dichtstoff dispersionsfarbe distanz doppelboden dose
draht draufsicht drainage dränage drehkipp druck druckfestigkeit dübel durchbruch
durchführung durchmesser ebene ecke edelstahl einbau einbaufertig einbauort
einfriedung einheit einheitspreis einlass einrichten einrichtung einsatz elastisch
elektro element endbeschichtung energie entkalkung entwässerung epoxidharz erdaushub
erdarbeiten erdstoff ersatz estrich fahrbahn fassade fassadenplatte fassung feder
feinsteinzeug fenster fensterbank fensterblech fertigfertigteil fertigstellung
feuchtigkeit filter filterkies flach flansch fliese fundament fugen fuge fussboden
fussleiste füllung gaube gebäude gefälle gehrung geländer genauigkeit gerüst
gesamtbetrag gesamtpreis geschäft gewerk gips gipskarton gitter gitterrost glas
glasur gleitlager graben grund grundierung grundriss guss gussasphalt hahn halter
hartschaum haustechnik heizkörper heizung herstellung hohlraum holz holzzarge
hülle imprägnierung industrie innen innenbereich innenausbau installation isolierung
kabel kabelschacht kabeltrasse kalk kanal kanalisation kante kautschuk kehle
keramik kies kitt klappe kleber klebemörtel klemm klempner klinker kombination
konstruktion körnung kunststoff kupplung kurztext lack lackierung lage langtext
lasur last latte lauf leim leiste leistung leistungsbereich leistungsbeschreibung
leistungsverzeichnis leitung leitungskanal licht linie los lüftung maler malerarbeiten
marmor masse mauer maueranschlussschiene mauerwerk mehraufwand menge metall mineralfaser
mineralwolle mischmörtel montage mörtel nachweis nachtrag nagel naturstein neigung
nennweite netz niveau nut nutzung oberboden oberfläche oberkante ordnungszahl ortbeton
paneel parkett parkettboden passstück pflaster plan planung platte podest porenbeton
position posten profil prüfung pvc qualität quer rabatte rahmen rand rauchmelder raum
raumung rechteck recycling reinigung reserve revisionsklappe revisionsöffnung richtung
ring rinnstein rohr rohrleitung rohbau rost roste rostschutz rücken rund sanierung
sanitär sauerstoff schalung schacht schachtabdeckung schachtbauwerk scheibe schicht
schiene schlitz schloss schlosser schluss schraube schreiner schrott schutz schutzlack
schweiss schwingung seite sektionaltor sicherheit sicherung silikon sockel spannung
sperrschicht spachtel stahl stahlbau stahlbeton stahltür stand stange stärke stein
stelle steuerung stift streichen streifen fundamente strich strom stufe stütze
symbol teppich teppichboden tiefbau toleranz tor träger trennwand tritt trockenbau
überdeckung übergang überhang übernahme übertrag umfassung unterbau unterboden
untergrund unterzug ventil verankerung verband verbindung verbund verfahren verfugen
vergabenummer vergießen verglasung verkleidung verlegen verlängerung vermessung
verputz verrechnungslohn verschluss vertrag vertraglich verwaltung vlies vob voll
voranstrich vorbereitung vorgehängt vorhaltung vorschrift wand wandbelag wandbekleidung
wandfliese wange wanne wärmedämmung wäsche wasser wasseranschluss wasserleitung
wasserwerk wechsel weite werk werkstoff werkzeug winkel witterung wohnung wurzel
zarge zement ziegel zink zirkulation zulage zuschlag zylinder
"""

GERMAN_WORDS: frozenset[str] = frozenset(_WORDS.split())
